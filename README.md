# SonarGrid

SonarGrid is a lightweight, centralized network information collection tool for device discovery, inventory observations, and inferred topology.

It is designed for environments where installing agents or probes on monitored networks is not allowed.

## Features

- Centralized agentless discovery
- SQLite storage
- Flask Web UI
- CIDR-based device discovery
- Device type detection by hostname, port fingerprint, and collected data
- Collection scheduler and worker
- Observation history
- Job run status and failure notifications
- SNMP v2c collection through `snmpwalk`
- Inferred L2/L3 topology without LLDP/CDP
- Topology freeze / resume
- CSV export
- systemd service install

## Requirements

- Linux
- Python 3.12+
- `python3-venv`
- `snmpwalk` for SNMP collection
- systemd for service mode

## Install

```bash
sudo ./install.sh
```

Default install path:

```text
/opt/sonargrid
```

The installer creates and starts:

```text
sonargrid.service
```

Open:

```text
http://<server-ip>:5000/
```

## Service Commands

```bash
sudo systemctl status sonargrid.service
sudo systemctl restart sonargrid.service
sudo systemctl stop sonargrid.service
```

## Manual Run

```bash
/opt/sonargrid/run-sonargrid.sh
```

## SNMP Community

Set SNMP v2c community in the Web UI:

```text
Settings -> SNMP v2c community
```

The value is not echoed back in the UI. It is encrypted before being stored in SQLite.

Environment fallback:

```bash
SONARGRID_SNMP_COMMUNITY=public /opt/sonargrid/run-sonargrid.sh
```

For systemd, prefer the Web UI setting.

## CLI

From the installed directory:

```bash
cd /opt/sonargrid
./.venv/bin/python app.py self-check
./.venv/bin/python app.py snmp-status
./.venv/bin/python app.py discover 192.168.1.0/24
./.venv/bin/python app.py add-job "Office discovery" 192.168.1.0/24 --interval 3600
./.venv/bin/python app.py add-collect-job "Collect all devices" all --interval 300
./.venv/bin/python app.py add-topology-job "Rebuild topology" --interval 300
./.venv/bin/python app.py worker-once
```

## Topology

SonarGrid does not use LLDP or CDP.

Topology is inferred from available information:

- device inventory
- IP/subnet relationships
- SNMP FDB data when available
- observations collected by jobs

When topology freeze is enabled, existing topology nodes and edges are preserved and no topology updates are written.

## Data

Default database:

```text
/opt/sonargrid/sonargrid.db
```

Secret key file:

```text
/opt/sonargrid/sonargrid.key
```

Do not commit either file.

## Uninstall

Remove application files but keep data:

```bash
sudo ./uninstall.sh
```

Remove application and data:

```bash
sudo ./uninstall.sh --purge
```

## Current Scope

SonarGrid currently focuses on information collection and inferred topology.

It does not implement full health monitoring, threshold alerting, SNMPv3 credential UI, or a production authentication system yet.
