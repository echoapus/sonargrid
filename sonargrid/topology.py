from __future__ import annotations

import ipaddress
import json

from .discovery import now


def get_setting(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def topology_frozen(conn) -> bool:
    return get_setting(conn, "topology.freeze", "0") == "1"


def set_topology_freeze(conn, frozen: bool) -> None:
    if frozen:
        snapshot_topology(conn, "freeze")
    set_setting(conn, "topology.freeze", "1" if frozen else "0")


def snapshot_topology(conn, reason: str) -> None:
    nodes = [dict(row) for row in conn.execute("SELECT * FROM topology_nodes ORDER BY id").fetchall()]
    edges = [dict(row) for row in conn.execute("SELECT * FROM topology_edges ORDER BY id").fetchall()]
    conn.execute(
        "INSERT INTO topology_snapshots (reason, created_at, data_json) VALUES (?, ?, ?)",
        (reason, now(), json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True)),
    )


def rebuild_topology(conn) -> dict:
    if topology_frozen(conn):
        return {"frozen": True, "nodes": 0, "edges": 0}

    timestamp = now()
    devices = conn.execute("SELECT * FROM devices WHERE archived_at IS NULL ORDER BY ip").fetchall()
    for device in devices:
        conn.execute(
            """
            INSERT INTO topology_nodes
                (device_id, label, node_type, status, confidence, source, updated_at)
            VALUES (?, ?, ?, ?, ?, 'inventory', ?)
            ON CONFLICT(device_id) DO UPDATE SET
                label = excluded.label,
                node_type = excluded.node_type,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                device["id"],
                device["hostname"] or device["ip"],
                device["device_type"],
                collection_status(device),
                device["detection_confidence"],
                timestamp,
            ),
        )

    nodes = conn.execute(
        """
        SELECT topology_nodes.id AS node_id, devices.ip
          FROM topology_nodes
          JOIN devices ON devices.id = topology_nodes.device_id
         WHERE devices.archived_at IS NULL
        """
    ).fetchall()
    edge_count = infer_snmp_edges(conn, timestamp)
    if edge_count == 0:
        edge_count = infer_shared_subnet_edges(conn, nodes, timestamp)
    node_count = conn.execute("SELECT COUNT(*) FROM topology_nodes").fetchone()[0]
    return {"frozen": False, "nodes": node_count, "edges": edge_count}


def infer_snmp_edges(conn, timestamp: str) -> int:
    rows = conn.execute(
        """
        SELECT observations.data_json
          FROM observations
         WHERE source = 'collection'
         ORDER BY observed_at DESC
         LIMIT 500
        """
    ).fetchall()
    mac_to_device = {}
    for device in conn.execute("SELECT id, mac FROM devices WHERE mac IS NOT NULL").fetchall():
        mac_to_device[normalize_mac(device["mac"])] = device["id"]

    edges = 0
    for row in rows:
        try:
            data = json.loads(row["data_json"])
        except json.JSONDecodeError:
            continue
        tables = data.get("snmp", {}).get("tables", {})
        fdb = tables.get("dot1dTpFdbTable") or []
        if not fdb:
            continue
        source_node = node_for_ip(conn, data.get("ip"))
        if not source_node:
            continue
        for item in fdb:
            mac = mac_from_oid(item.get("oid", ""))
            target_device_id = mac_to_device.get(mac)
            if not target_device_id:
                continue
            target_node = node_for_device(conn, target_device_id)
            if not target_node or target_node == source_node:
                continue
            conn.execute(
                """
                INSERT INTO topology_edges
                    (source_node_id, target_node_id, relation, confidence, source, notes, updated_at)
                VALUES (?, ?, 'snmp_fdb', 'medium', 'snmp_fdb', ?, ?)
                ON CONFLICT(source_node_id, target_node_id, relation) DO UPDATE SET
                    confidence = excluded.confidence,
                    source = excluded.source,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (source_node, target_node, f"FDB MAC {mac}", timestamp),
            )
            edges += 1
    return edges


def node_for_ip(conn, ip: str | None) -> int | None:
    if not ip:
        return None
    row = conn.execute(
        """
        SELECT topology_nodes.id
          FROM topology_nodes
          JOIN devices ON devices.id = topology_nodes.device_id
         WHERE devices.ip = ?
        """,
        (ip,),
    ).fetchone()
    return row["id"] if row else None


def node_for_device(conn, device_id: int) -> int | None:
    row = conn.execute("SELECT id FROM topology_nodes WHERE device_id = ?", (device_id,)).fetchone()
    return row["id"] if row else None


def mac_from_oid(oid: str) -> str:
    parts = oid.split(".")[-6:]
    try:
        return ":".join(f"{int(part):02x}" for part in parts)
    except ValueError:
        return ""


def normalize_mac(mac: str) -> str:
    clean = mac.lower().replace("-", ":").replace(".", "")
    if ":" in clean:
        return ":".join(part.zfill(2) for part in clean.split(":"))
    if len(clean) == 12:
        return ":".join(clean[i : i + 2] for i in range(0, 12, 2))
    return clean


def collection_status(device) -> str:
    if device["inactive_at"]:
        return "inactive"
    if device["last_seen_at"]:
        return "collected"
    return "unknown"


def infer_shared_subnet_edges(conn, nodes, timestamp: str) -> int:
    # ponytail: /24 subnet inference until SNMP FDB/ARP collectors are wired.
    buckets: dict[str, list[int]] = {}
    for node in nodes:
        try:
            ip = ipaddress.ip_address(node["ip"])
        except ValueError:
            continue
        if ip.version != 4:
            continue
        subnet = ".".join(str(ip).split(".")[:3])
        buckets.setdefault(subnet, []).append(node["node_id"])

    count = 0
    for subnet, node_ids in buckets.items():
        if len(node_ids) < 2:
            continue
        root = sorted(node_ids)[0]
        for target in sorted(node_ids)[1:]:
            conn.execute(
                """
                INSERT INTO topology_edges
                    (source_node_id, target_node_id, relation, confidence, source, notes, updated_at)
                VALUES (?, ?, 'shared_subnet', 'low', 'ip_subnet', ?, ?)
                ON CONFLICT(source_node_id, target_node_id, relation) DO UPDATE SET
                    confidence = excluded.confidence,
                    source = excluded.source,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (root, target, f"inferred /24 subnet {subnet}.0", timestamp),
            )
            count += 1
    return count
