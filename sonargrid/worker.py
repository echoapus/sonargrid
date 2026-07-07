from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

from .collector import collect_device_info, save_observation
from .discovery import discover_range, mark_inactive_devices, now, upsert_discovery
from .notify import notify_failure
from .topology import rebuild_topology


def due_jobs(conn) -> list:
    timestamp = now()
    return conn.execute(
        """
        SELECT * FROM collection_jobs
         WHERE enabled = 1
           AND (next_run_at IS NULL OR next_run_at <= ?)
         ORDER BY COALESCE(next_run_at, created_at)
        """,
        (timestamp,),
    ).fetchall()


def create_discovery_job(conn, name: str, target: str, interval_seconds: int = 3600) -> int:
    timestamp = now()
    cur = conn.execute(
        """
        INSERT INTO collection_jobs
            (name, job_type, target, interval_seconds, next_run_at, created_at, updated_at)
        VALUES (?, 'discovery', ?, ?, ?, ?, ?)
        """,
        (name, target, interval_seconds, timestamp, timestamp, timestamp),
    )
    return cur.lastrowid


def create_collection_job(conn, name: str = "Collect device info", target: str = "all", interval_seconds: int = 300) -> int:
    timestamp = now()
    cur = conn.execute(
        """
        INSERT INTO collection_jobs
            (name, job_type, target, interval_seconds, next_run_at, created_at, updated_at)
        VALUES (?, 'collect_info', ?, ?, ?, ?, ?)
        """,
        (name, target, interval_seconds, timestamp, timestamp, timestamp),
    )
    return cur.lastrowid


def create_topology_job(conn, name: str = "Rebuild topology", interval_seconds: int = 300) -> int:
    timestamp = now()
    cur = conn.execute(
        """
        INSERT INTO collection_jobs
            (name, job_type, target, interval_seconds, next_run_at, created_at, updated_at)
        VALUES (?, 'topology', 'all', ?, ?, ?, ?)
        """,
        (name, interval_seconds, timestamp, timestamp, timestamp),
    )
    return cur.lastrowid


def run_job(conn, job) -> dict:
    started = now()
    run_id = conn.execute(
        """
        INSERT INTO job_runs (job_id, job_type, target, status, started_at)
        VALUES (?, ?, ?, 'running', ?)
        """,
        (job["id"], job["job_type"], job["target"], started),
    ).lastrowid
    conn.commit()

    try:
        if job["job_type"] == "discovery":
            payload = run_discovery(conn, job["target"])
        elif job["job_type"] == "collect_info":
            payload = run_collection(conn, job["target"])
        elif job["job_type"] == "topology":
            payload = rebuild_topology(conn)
        else:
            raise ValueError(f"unsupported job type: {job['job_type']}")
        status = "success"
        error = ""
    except Exception as exc:  # noqa: BLE001 - stored for operator visibility
        payload = {}
        status = "failed"
        error = str(exc)

    finished = now()
    next_run = (datetime.now(UTC) + timedelta(seconds=job["interval_seconds"])).isoformat()
    conn.execute(
        """
        UPDATE job_runs
           SET status = ?, finished_at = ?, error = ?, result_json = ?
         WHERE id = ?
        """,
        (status, finished, error, json.dumps(payload), run_id),
    )
    failures = 0 if status == "success" else job["consecutive_failures"] + 1
    conn.execute(
        """
        UPDATE collection_jobs
           SET last_run_at = ?,
               last_success_at = CASE WHEN ? = 'success' THEN ? ELSE last_success_at END,
               last_error = ?,
               consecutive_failures = ?,
               next_run_at = ?,
               updated_at = ?
         WHERE id = ?
        """,
        (finished, status, finished, error, failures, next_run, finished, job["id"]),
    )
    if status == "failed" or failures >= 3:
        notify_failure(conn, run_id, f"SonarGrid job {job['name']} failed: {error or failures}")
    conn.commit()
    return {"status": status, "error": error, **payload}


def run_discovery(conn, target: str) -> dict:
    results = discover_range(target)
    saved = 0
    for result in results:
        if upsert_discovery(conn, result):
            saved += 1
    inactive = mark_inactive_devices(conn)
    return {
        "scanned": len(results),
        "responded": sum(1 for result in results if result.responded),
        "saved": saved,
        "marked_inactive": inactive,
    }


def run_collection(conn, target: str) -> dict:
    if target == "all":
        devices = conn.execute(
            "SELECT * FROM devices WHERE inactive_at IS NULL AND archived_at IS NULL ORDER BY ip"
        ).fetchall()
    else:
        devices = conn.execute(
            "SELECT * FROM devices WHERE ip = ? AND archived_at IS NULL",
            (target,),
        ).fetchall()
    observed_at = now()
    collected = 0
    failed = 0
    for device in devices:
        try:
            data = collect_device_info(device, conn)
            save_observation(conn, device["id"], observed_at, data)
            if data["ping"]["responded"]:
                conn.execute(
                    "UPDATE devices SET last_seen_at = ?, inactive_at = NULL, updated_at = ? WHERE id = ?",
                    (observed_at, observed_at, device["id"]),
                )
            collected += 1
        except Exception:  # noqa: BLE001 - count per-device failure without stopping the batch
            failed += 1
    inactive = mark_inactive_devices(conn)
    return {"devices": len(devices), "collected": collected, "failed": failed, "marked_inactive": inactive}


def run_due_jobs(conn) -> list[dict]:
    return [run_job(conn, job) for job in due_jobs(conn)]


def run_loop(conn_factory, sleep_seconds: int = 10) -> None:
    while True:
        with conn_factory() as conn:
            run_due_jobs(conn)
        time.sleep(sleep_seconds)
