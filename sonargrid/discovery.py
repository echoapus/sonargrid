from __future__ import annotations

import ipaddress
import platform
import socket
import json
import subprocess
from dataclasses import dataclass, asdict
from datetime import UTC, datetime, timedelta


COMMON_PORTS = {
    22: "ssh",
    80: "http",
    443: "https",
    445: "smb",
    515: "printer_lpd",
    631: "printer_ipp",
    9100: "printer_raw",
    3389: "rdp",
    5985: "winrm",
    5986: "winrm_tls",
}


@dataclass
class DiscoveryResult:
    ip: str
    responded: bool
    hostname: str | None
    open_ports: list[int]
    device_type: str
    confidence: str
    source: str
    notes: str


def now() -> str:
    return datetime.now(UTC).isoformat()


def iter_hosts(target: str) -> list[str]:
    network = ipaddress.ip_network(target, strict=False)
    return [str(ip) for ip in network.hosts()]


def ping(ip: str, timeout: int = 1) -> bool:
    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), ip]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def scan_ports(ip: str, timeout: float = 0.25) -> list[int]:
    open_ports: list[int] = []
    for port in COMMON_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            if sock.connect_ex((ip, port)) == 0:
                open_ports.append(port)
    return open_ports


def reverse_dns(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, TimeoutError):
        return None


def classify(hostname: str | None, open_ports: list[int]) -> tuple[str, str, str, str]:
    labels = [COMMON_PORTS[p] for p in open_ports if p in COMMON_PORTS]
    name = (hostname or "").lower()

    if {9100, 515, 631} & set(open_ports) or name.startswith(("prn-", "prt-", "printer-")):
        return "printer", "high", "port" if open_ports else "hostname", ",".join(labels)
    if name.startswith(("srv-", "server-")):
        return "server", "medium", "hostname", hostname or ""
    if name.startswith(("pc-", "nb-", "laptop-")):
        return "pc", "medium", "hostname", hostname or ""
    if 3389 in open_ports or 5985 in open_ports or 5986 in open_ports:
        return "pc", "low", "port", ",".join(labels)
    if 22 in open_ports and (80 in open_ports or 443 in open_ports):
        return "server", "low", "port", ",".join(labels)
    return "unknown", "low", "icmp" if open_ports else "unknown", ",".join(labels)


def discover_host(ip: str) -> DiscoveryResult:
    responded = ping(ip)
    open_ports = scan_ports(ip) if responded else []
    hostname = reverse_dns(ip) if responded else None
    device_type, confidence, source, notes = classify(hostname, open_ports)
    return DiscoveryResult(ip, responded, hostname, open_ports, device_type, confidence, source, notes)


def discover_range(target: str) -> list[DiscoveryResult]:
    return [discover_host(ip) for ip in iter_hosts(target)]


def upsert_discovery(conn, result: DiscoveryResult) -> int | None:
    if not result.responded:
        return None
    timestamp = now()
    existing = conn.execute("SELECT id FROM devices WHERE ip = ?", (result.ip,)).fetchone()
    if existing:
        device_id = existing["id"]
        conn.execute(
            """
            UPDATE devices
               SET hostname = COALESCE(?, hostname),
                   device_type = ?,
                   detection_confidence = ?,
                   detection_source = ?,
                   detection_notes = ?,
                   last_seen_at = ?,
                   inactive_at = NULL,
                   updated_at = ?
             WHERE id = ?
            """,
            (
                result.hostname,
                result.device_type,
                result.confidence,
                result.source,
                result.notes,
                timestamp,
                timestamp,
                device_id,
            ),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO devices (
                ip, hostname, device_type, detection_confidence, detection_source,
                detection_notes, first_seen_at, last_seen_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.ip,
                result.hostname,
                result.device_type,
                result.confidence,
                result.source,
                result.notes,
                timestamp,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        device_id = cur.lastrowid

    conn.execute(
        """
        INSERT INTO device_type_detections
            (device_id, device_type, confidence, source, notes, detected_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (device_id, result.device_type, result.confidence, result.source, result.notes, timestamp),
    )
    conn.execute(
        "INSERT INTO observations (device_id, source, observed_at, data_json) VALUES (?, ?, ?, ?)",
        (device_id, "discovery", timestamp, json.dumps(asdict(result), sort_keys=True)),
    )
    return device_id


def mark_inactive_devices(conn, days: int = 3) -> int:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    timestamp = now()
    cur = conn.execute(
        """
        UPDATE devices
           SET inactive_at = ?, updated_at = ?
         WHERE inactive_at IS NULL
           AND last_seen_at IS NOT NULL
           AND last_seen_at < ?
        """,
        (timestamp, timestamp, cutoff),
    )
    return cur.rowcount
