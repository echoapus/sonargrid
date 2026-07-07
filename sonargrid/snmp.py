from __future__ import annotations

import os
import subprocess

from .secrets_store import get_secret

OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "ifTable": "1.3.6.1.2.1.2.2.1",
    "ipNetToMediaTable": "1.3.6.1.2.1.4.22.1",
    "dot1dTpFdbTable": "1.3.6.1.2.1.17.4.3.1",
    "dot1dBasePortTable": "1.3.6.1.2.1.17.1.4.1.2",
}


def collect_snmp(ip: str, conn=None, timeout: int = 2) -> dict:
    community = get_snmp_community(conn)
    if not community:
        return {"enabled": False, "reason": "SNMP community not set"}

    data = {"enabled": True, "tables": {}, "errors": {}}
    for name, oid in OIDS.items():
        cmd = ["snmpwalk", "-v2c", "-c", community, "-t", "1", "-r", "0", ip, oid]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            data["errors"][name] = str(exc)
            continue
        if proc.returncode == 0:
            data["tables"][name] = parse_snmpwalk(proc.stdout)
        else:
            data["errors"][name] = proc.stderr.strip() or proc.stdout.strip()
    return data


def get_snmp_community(conn=None) -> str | None:
    if conn is not None:
        secret = get_secret(conn, "snmp.community")
        if secret:
            return secret
    return os.environ.get("SONARGRID_SNMP_COMMUNITY")


def parse_snmpwalk(output: str) -> list[dict]:
    rows = []
    for line in output.splitlines():
        if " = " not in line:
            continue
        oid, value = line.split(" = ", 1)
        rows.append({"oid": oid.strip(), "value": value.strip()})
    return rows
