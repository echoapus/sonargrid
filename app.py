from __future__ import annotations

import argparse
import csv
import io
import json
import threading

from flask import Flask, Response, redirect, render_template_string, request, url_for

from sonargrid.db import connect, init_db
from sonargrid.discovery import discover_range, mark_inactive_devices, upsert_discovery
from sonargrid.secrets_store import has_secret, set_secret
from sonargrid.topology import rebuild_topology, set_topology_freeze, topology_frozen
from sonargrid.worker import create_collection_job, create_discovery_job, create_topology_job, run_due_jobs, run_loop

app = Flask(__name__)


INDEX = """
<!doctype html>
<title>SonarGrid NMS</title>
<h1>SonarGrid NMS</h1>
<h2>Dashboard</h2>
<ul>
  <li>Total devices: {{ summary.devices }}</li>
  <li>Inactive devices: {{ summary.inactive }}</li>
  <li>Observations: {{ summary.observations }}</li>
  <li>Successful job runs: {{ summary.success_runs }}</li>
  <li>Failed job runs: {{ summary.failed_runs }}</li>
  <li>Topology: {{ summary.topology_nodes }} nodes / {{ summary.topology_edges }} edges</li>
  <li>Topology freeze: {{ "on" if frozen else "off" }}</li>
</ul>
<p>
  <a href="{{ url_for('export_devices') }}">Export devices CSV</a>
  <a href="{{ url_for('export_observations') }}">Export observations CSV</a>
</p>
<h2>Settings</h2>
<form method="post" action="{{ url_for('save_snmp_settings') }}">
  <label>SNMP v2c community
    <input name="community" type="password" placeholder="{{ 'configured' if snmp_configured else 'not configured' }}">
  </label>
  <button>Save SNMP community</button>
</form>
<p>SNMP community configured: {{ "yes" if snmp_configured else "no" }}</p>
<form method="post" action="{{ url_for('add_job') }}">
  <label>Name <input name="name" value="Local discovery"></label>
  <label>CIDR <input name="target" value="127.0.0.0/30"></label>
  <label>Interval seconds <input name="interval_seconds" value="3600" type="number"></label>
  <button>Add discovery job</button>
</form>
<form method="post" action="{{ url_for('add_collect_job') }}">
  <label>Name <input name="name" value="Collect all devices"></label>
  <label>Target <input name="target" value="all"></label>
  <label>Interval seconds <input name="interval_seconds" value="300" type="number"></label>
  <button>Add collection job</button>
</form>
<form method="post" action="{{ url_for('add_topology_job') }}">
  <label>Name <input name="name" value="Rebuild topology"></label>
  <label>Interval seconds <input name="interval_seconds" value="300" type="number"></label>
  <button>Add topology job</button>
</form>
<form method="post" action="{{ url_for('rebuild_topology_now') }}">
  <button>Rebuild topology now</button>
</form>
<form method="post" action="{{ url_for('toggle_topology_freeze') }}">
  <input type="hidden" name="freeze" value="{{ '0' if frozen else '1' }}">
  <button>{{ "Resume topology updates" if frozen else "Pause topology updates" }}</button>
</form>
<h2>Devices</h2>
<table border="1" cellpadding="4">
<tr><th>IP</th><th>Hostname</th><th>Type</th><th>Confidence</th><th>Source</th><th>Last seen</th><th>Inactive</th></tr>
{% for d in devices %}
<tr>
  <td>{{ d.ip }}</td><td>{{ d.hostname or "" }}</td><td>{{ d.device_type }}</td>
  <td>{{ d.detection_confidence }}</td><td>{{ d.detection_source }}</td>
  <td>{{ d.last_seen_at or "" }}</td><td>{{ d.inactive_at or "" }}</td>
</tr>
{% endfor %}
</table>
<h2>Topology</h2>
<table border="1" cellpadding="4">
<tr><th>Node</th><th>Type</th><th>Status</th><th>Confidence</th><th>Updated</th></tr>
{% for n in topology_nodes %}
<tr><td>{{ n.label }}</td><td>{{ n.node_type }}</td><td>{{ n.status }}</td><td>{{ n.confidence }}</td><td>{{ n.updated_at }}</td></tr>
{% endfor %}
</table>
<table border="1" cellpadding="4">
<tr><th>Source</th><th>Target</th><th>Relation</th><th>Confidence</th><th>Notes</th></tr>
{% for e in topology_edges %}
<tr><td>{{ e.source_label }}</td><td>{{ e.target_label }}</td><td>{{ e.relation }}</td><td>{{ e.confidence }}</td><td>{{ e.notes }}</td></tr>
{% endfor %}
</table>
<h2>Jobs</h2>
<table border="1" cellpadding="4">
<tr><th>Name</th><th>Type</th><th>Target</th><th>Next run</th><th>Last success</th><th>Failures</th><th>Last error</th></tr>
{% for j in jobs %}
<tr><td>{{ j.name }}</td><td>{{ j.job_type }}</td><td>{{ j.target }}</td><td>{{ j.next_run_at or "" }}</td><td>{{ j.last_success_at or "" }}</td><td>{{ j.consecutive_failures }}</td><td>{{ j.last_error }}</td></tr>
{% endfor %}
</table>
<h2>Recent job runs</h2>
<table border="1" cellpadding="4">
<tr><th>Type</th><th>Target</th><th>Status</th><th>Started</th><th>Error</th><th>Result</th></tr>
{% for r in runs %}
<tr><td>{{ r.job_type }}</td><td>{{ r.target }}</td><td>{{ r.status }}</td><td>{{ r.started_at }}</td><td>{{ r.error }}</td><td>{{ r.result_json }}</td></tr>
{% endfor %}
</table>
<h2>Notifications</h2>
<table border="1" cellpadding="4">
<tr><th>Channel</th><th>Status</th><th>Sent</th><th>Message</th><th>Error</th></tr>
{% for n in notifications %}
<tr><td>{{ n.channel }}</td><td>{{ n.status }}</td><td>{{ n.sent_at }}</td><td>{{ n.message }}</td><td>{{ n.error }}</td></tr>
{% endfor %}
</table>
"""


@app.get("/")
def index():
    with connect() as conn:
        summary = dashboard_summary(conn)
        devices = conn.execute("SELECT * FROM devices ORDER BY ip").fetchall()
        jobs = conn.execute("SELECT * FROM collection_jobs ORDER BY id DESC").fetchall()
        runs = conn.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT 20").fetchall()
        notifications = conn.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 20").fetchall()
        nodes = conn.execute("SELECT * FROM topology_nodes ORDER BY label").fetchall()
        edges = conn.execute(
            """
            SELECT e.*, s.label AS source_label, t.label AS target_label
              FROM topology_edges e
              JOIN topology_nodes s ON s.id = e.source_node_id
              JOIN topology_nodes t ON t.id = e.target_node_id
             ORDER BY s.label, t.label
            """
        ).fetchall()
        frozen = topology_frozen(conn)
        snmp_configured = has_secret(conn, "snmp.community")
    return render_template_string(
        INDEX,
        summary=summary,
        frozen=frozen,
        devices=devices,
        jobs=jobs,
        runs=runs,
        notifications=notifications,
        topology_nodes=nodes,
        topology_edges=edges,
        snmp_configured=snmp_configured,
    )


def dashboard_summary(conn) -> dict:
    return {
        "devices": conn.execute("SELECT COUNT(*) FROM devices WHERE archived_at IS NULL").fetchone()[0],
        "inactive": conn.execute("SELECT COUNT(*) FROM devices WHERE inactive_at IS NOT NULL AND archived_at IS NULL").fetchone()[0],
        "observations": conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
        "success_runs": conn.execute("SELECT COUNT(*) FROM job_runs WHERE status = 'success'").fetchone()[0],
        "failed_runs": conn.execute("SELECT COUNT(*) FROM job_runs WHERE status = 'failed'").fetchone()[0],
        "topology_nodes": conn.execute("SELECT COUNT(*) FROM topology_nodes").fetchone()[0],
        "topology_edges": conn.execute("SELECT COUNT(*) FROM topology_edges").fetchone()[0],
    }


@app.post("/jobs")
def add_job():
    with connect() as conn:
        create_discovery_job(
            conn,
            request.form["name"],
            request.form["target"],
            int(request.form.get("interval_seconds") or 3600),
        )
        conn.commit()
    return redirect(url_for("index"))


@app.post("/jobs/collect")
def add_collect_job():
    with connect() as conn:
        create_collection_job(
            conn,
            request.form["name"],
            request.form["target"],
            int(request.form.get("interval_seconds") or 300),
        )
        conn.commit()
    return redirect(url_for("index"))


@app.post("/jobs/topology")
def add_topology_job():
    with connect() as conn:
        create_topology_job(
            conn,
            request.form["name"],
            int(request.form.get("interval_seconds") or 300),
        )
        conn.commit()
    return redirect(url_for("index"))


@app.post("/topology/rebuild")
def rebuild_topology_now():
    with connect() as conn:
        rebuild_topology(conn)
        conn.commit()
    return redirect(url_for("index"))


@app.post("/topology/freeze")
def toggle_topology_freeze():
    with connect() as conn:
        set_topology_freeze(conn, request.form.get("freeze") == "1")
        conn.commit()
    return redirect(url_for("index"))


@app.post("/settings/snmp")
def save_snmp_settings():
    community = request.form.get("community", "")
    if community:
        with connect() as conn:
            set_secret(conn, "snmp.community", community)
            conn.commit()
    return redirect(url_for("index"))


@app.get("/export/devices.csv")
def export_devices():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY ip").fetchall()
    return csv_response("devices.csv", rows)


@app.get("/export/observations.csv")
def export_observations():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT observations.id, devices.ip, observations.source, observations.observed_at, observations.data_json
              FROM observations
              LEFT JOIN devices ON devices.id = observations.device_id
             ORDER BY observations.id DESC
            """
        ).fetchall()
    return csv_response("observations.csv", rows)


def csv_response(filename: str, rows) -> Response:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def cmd_init_db(_args) -> None:
    init_db()
    print("initialized sonargrid.db")


def cmd_discover(args) -> None:
    init_db()
    with connect() as conn:
        results = discover_range(args.target)
        for result in results:
            upsert_discovery(conn, result)
        inactive = mark_inactive_devices(conn)
        conn.commit()
    print(json.dumps({"scanned": len(results), "marked_inactive": inactive}, indent=2))


def cmd_add_job(args) -> None:
    init_db()
    with connect() as conn:
        job_id = create_discovery_job(conn, args.name, args.target, args.interval)
        conn.commit()
    print(f"created job {job_id}")


def cmd_add_collect_job(args) -> None:
    init_db()
    with connect() as conn:
        job_id = create_collection_job(conn, args.name, args.target, args.interval)
        conn.commit()
    print(f"created collection job {job_id}")


def cmd_add_topology_job(args) -> None:
    init_db()
    with connect() as conn:
        job_id = create_topology_job(conn, args.name, args.interval)
        conn.commit()
    print(f"created topology job {job_id}")


def cmd_worker_once(_args) -> None:
    init_db()
    with connect() as conn:
        print(json.dumps(run_due_jobs(conn), indent=2))


def cmd_snmp_status(_args) -> None:
    import os

    with connect() as conn:
        configured = has_secret(conn, "snmp.community")
    print(json.dumps({
        "snmpwalk": bool(__import__("shutil").which("snmpwalk")),
        "webui_community": configured,
        "SONARGRID_SNMP_COMMUNITY": bool(os.environ.get("SONARGRID_SNMP_COMMUNITY")),
    }, indent=2))


def cmd_serve(args) -> None:
    init_db()
    if args.worker:
        threading.Thread(target=run_loop, args=(connect,), daemon=True).start()
    app.run(host=args.host, port=args.port, debug=args.debug)


def cmd_self_check(_args) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO devices (
                ip, hostname, device_type, detection_confidence, detection_source,
                first_seen_at, last_seen_at, created_at, updated_at
            ) VALUES ('127.0.0.1', 'localhost', 'server', 'medium', 'self-check',
                      datetime('now'), datetime('now'), datetime('now'), datetime('now'))
            """
        )
        job_id = create_discovery_job(conn, "self-check", "127.0.0.0/30", 3600)
        assert job_id > 0
        collect_job_id = create_collection_job(conn, "self-check collect", "all", 3600)
        assert collect_job_id > 0
        topology_job_id = create_topology_job(conn, "self-check topology", 3600)
        assert topology_job_id > 0
        conn.execute(
            """
            INSERT INTO collection_jobs
                (name, job_type, target, interval_seconds, next_run_at, created_at, updated_at)
            VALUES ('self-check fail', 'bad_type', 'none', 3600, datetime('now'), datetime('now'), datetime('now'))
            """
        )
        runs = run_due_jobs(conn)
        assert runs and {run["status"] for run in runs} <= {"success", "failed"}
        assert conn.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0] >= 1
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] >= 1
        assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] >= 1
        set_secret(conn, "snmp.community", "public")
        assert has_secret(conn, "snmp.community")
        rebuild_topology(conn)
        assert conn.execute("SELECT COUNT(*) FROM topology_nodes").fetchone()[0] >= 1
        set_topology_freeze(conn, True)
        frozen_result = rebuild_topology(conn)
        assert frozen_result["frozen"] is True
        set_topology_freeze(conn, False)
    print("self-check ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)

    init_parser = sub.add_parser("init-db")
    init_parser.set_defaults(func=cmd_init_db)

    discover_parser = sub.add_parser("discover")
    discover_parser.add_argument("target")
    discover_parser.set_defaults(func=cmd_discover)

    add_job_parser = sub.add_parser("add-job")
    add_job_parser.add_argument("name")
    add_job_parser.add_argument("target")
    add_job_parser.add_argument("--interval", type=int, default=3600)
    add_job_parser.set_defaults(func=cmd_add_job)

    add_collect_parser = sub.add_parser("add-collect-job")
    add_collect_parser.add_argument("name")
    add_collect_parser.add_argument("target", nargs="?", default="all")
    add_collect_parser.add_argument("--interval", type=int, default=300)
    add_collect_parser.set_defaults(func=cmd_add_collect_job)

    add_topology_parser = sub.add_parser("add-topology-job")
    add_topology_parser.add_argument("name")
    add_topology_parser.add_argument("--interval", type=int, default=300)
    add_topology_parser.set_defaults(func=cmd_add_topology_job)

    worker_parser = sub.add_parser("worker-once")
    worker_parser.set_defaults(func=cmd_worker_once)

    snmp_parser = sub.add_parser("snmp-status")
    snmp_parser.set_defaults(func=cmd_snmp_status)

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=5000)
    serve_parser.add_argument("--debug", action="store_true")
    serve_parser.add_argument("--worker", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)

    self_check_parser = sub.add_parser("self-check")
    self_check_parser.set_defaults(func=cmd_self_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
