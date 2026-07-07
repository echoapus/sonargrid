from __future__ import annotations

import json
import socket
import subprocess
import time

from .discovery import COMMON_PORTS, reverse_dns, scan_ports
from .snmp import collect_snmp


def ping_response(ip: str, timeout: int = 1) -> dict:
    started = time.monotonic()
    proc = subprocess.run(
        ["ping", "-c", "1", "-W", str(timeout), ip],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    return {"responded": proc.returncode == 0, "response_time_ms": elapsed_ms}


def collect_device_info(device, conn=None) -> dict:
    ip = device["ip"]
    ping = ping_response(ip)
    open_ports = scan_ports(ip) if ping["responded"] else []
    return {
        "ip": ip,
        "hostname": reverse_dns(ip) if ping["responded"] else device["hostname"],
        "device_type": device["device_type"],
        "ping": ping,
        "open_ports": open_ports,
        "open_services": [COMMON_PORTS[p] for p in open_ports],
        "snmp": collect_snmp(ip, conn) if ping["responded"] else {"enabled": False, "reason": "no ping response"},
        "wmi": {},
        "ssh": {},
    }


def save_observation(conn, device_id: int, observed_at: str, data: dict) -> None:
    conn.execute(
        "INSERT INTO observations (device_id, source, observed_at, data_json) VALUES (?, ?, ?, ?)",
        (device_id, "collection", observed_at, json.dumps(data, sort_keys=True)),
    )
