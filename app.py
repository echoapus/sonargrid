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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SonarGrid NMS</title>
<style>
  :root {
    --bg: #f5f7f9;
    --surface: #fbfcfd;
    --panel: #ffffff;
    --panel-soft: #f7f9fb;
    --line: #d7dee8;
    --line-soft: #e9eef4;
    --text: #151b23;
    --muted: #66707f;
    --soft-text: #344054;
    --accent: #087f8c;
    --accent-strong: #06626d;
    --accent-soft: #e6f6f8;
    --ok: #087443;
    --ok-soft: #e7f6ee;
    --warn: #9a6700;
    --warn-soft: #fff4d6;
    --bad: #b42318;
    --bad-soft: #ffebe8;
    --graphite: #181818;
    --graphite-2: #242424;
    --shadow: 0 1px 2px rgba(20, 28, 38, .05), 0 10px 28px rgba(20, 28, 38, .06);
    --focus: 0 0 0 3px rgba(8, 127, 140, .16);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-width: 320px;
    background: var(--bg);
    color: var(--text);
    font: 14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    letter-spacing: 0;
  }
  a { color: var(--accent); text-decoration: none; font-weight: 650; }
  a:hover { color: var(--accent-strong); text-decoration: underline; }
  .shell { display: grid; grid-template-columns: 248px minmax(0, 1fr); min-height: 100vh; }
  .sidebar {
    background: var(--graphite);
    color: #f9fafb;
    padding: 22px 16px;
    position: sticky;
    top: 0;
    height: 100vh;
    border-right: 1px solid #2f2f2f;
  }
  .brand { display: flex; align-items: center; gap: 11px; margin-bottom: 30px; }
  .mark {
    width: 36px; height: 36px; border-radius: 8px;
    display: grid; place-items: center;
    background: var(--accent-soft); color: var(--accent-strong); font-weight: 900;
    border: 1px solid rgba(255,255,255,.18);
  }
  .brand-title { font-size: 18px; font-weight: 800; }
  .brand-sub { color: #a8b0bb; font-size: 12px; margin-top: 1px; }
  .nav { display: grid; gap: 5px; }
  .nav a {
    color: #d7dce3;
    padding: 10px 11px;
    border-radius: 6px;
    font-weight: 650;
    border: 1px solid transparent;
  }
  .nav a:hover { background: var(--graphite-2); color: #fff; text-decoration: none; border-color: #333; }
  .main { min-width: 0; }
  .topbar {
    min-height: 70px;
    background: rgba(251, 252, 253, .88);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--line);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 12px 26px;
    position: sticky;
    top: 0;
    z-index: 4;
  }
  h1 { font-size: 21px; line-height: 1.2; margin: 0; font-weight: 820; }
  h2 { font-size: 15px; margin: 0; font-weight: 780; }
  .muted { color: var(--muted); }
  .content { padding: 26px; display: grid; gap: 20px; }
  .stats {
    display: grid;
    grid-template-columns: repeat(6, minmax(136px, 1fr));
    gap: 12px;
  }
  .stat {
    background: var(--panel);
    border: 1px solid var(--line-soft);
    border-radius: 8px;
    box-shadow: var(--shadow);
    padding: 15px 15px 13px;
    min-height: 96px;
    position: relative;
    overflow: hidden;
  }
  .stat::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 3px;
    background: var(--accent);
  }
  .stat-label { color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; }
  .stat-value { font-size: 30px; line-height: 1.08; font-weight: 860; margin-top: 12px; letter-spacing: 0; }
  .grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(340px, .8fr); gap: 20px; align-items: start; }
  .panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: var(--shadow);
    overflow: hidden;
  }
  .panel:hover { border-color: #cbd5e1; }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 13px 16px;
    border-bottom: 1px solid var(--line-soft);
    background: var(--panel-soft);
  }
  .panel-body { padding: 16px; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .forms { display: grid; gap: 14px; }
  form.inline { display: grid; grid-template-columns: repeat(3, minmax(140px, 1fr)) auto; gap: 10px; align-items: end; }
  form.compact { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
  label { display: grid; gap: 5px; color: var(--muted); font-size: 12px; font-weight: 700; }
  input {
    width: 100%;
    min-height: 38px;
    border: 1px solid #cad3df;
    border-radius: 6px;
    padding: 8px 10px;
    color: var(--text);
    background: #fff;
    font: inherit;
  }
  input:focus { outline: none; border-color: var(--accent); box-shadow: var(--focus); }
  button, .button {
    min-height: 38px;
    border: 1px solid var(--accent);
    border-radius: 6px;
    padding: 8px 13px;
    color: #fff;
    background: var(--accent);
    font-weight: 760;
    cursor: pointer;
    white-space: nowrap;
    box-shadow: 0 1px 1px rgba(0,0,0,.04);
  }
  button:hover, .button:hover { background: var(--accent-strong); text-decoration: none; transform: translateY(-1px); }
  button.secondary, .button.secondary {
    background: #fff;
    color: var(--accent);
  }
  button.warning { background: #fff; border-color: var(--warn); color: var(--warn); }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; min-width: 760px; }
  th {
    position: sticky;
    top: 70px;
    z-index: 2;
    text-align: left;
    color: var(--muted);
    font-size: 12px;
    font-weight: 800;
    background: var(--panel-soft);
    border-bottom: 1px solid var(--line);
    padding: 10px 12px;
    white-space: nowrap;
  }
  td {
    border-bottom: 1px solid var(--line-soft);
    padding: 11px 12px;
    vertical-align: top;
    white-space: nowrap;
  }
  tbody tr:hover, tr:hover td { background: #fbfdff; }
  tr:last-child td { border-bottom: 0; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
  .truncate { max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pill {
    display: inline-flex;
    align-items: center;
    min-height: 24px;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 800;
    background: #eef2f6;
    color: var(--soft-text);
    border: 1px solid rgba(52,64,84,.08);
  }
  .pill.ok { background: var(--ok-soft); color: var(--ok); }
  .pill.warn { background: var(--warn-soft); color: var(--warn); }
  .pill.bad { background: var(--bad-soft); color: var(--bad); }
  .split { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 1120px) {
    .stats { grid-template-columns: repeat(3, 1fr); }
    .grid, .split { grid-template-columns: 1fr; }
  }
  @media (max-width: 760px) {
    .shell { grid-template-columns: 1fr; }
    .sidebar { position: static; height: auto; }
    .nav { grid-template-columns: repeat(3, 1fr); }
    .topbar { position: static; align-items: flex-start; height: auto; padding: 16px; flex-direction: column; }
    .content { padding: 16px; }
    .stats { grid-template-columns: 1fr 1fr; }
    form.inline { grid-template-columns: 1fr; }
  }
</style>
<div class="shell">
  <aside class="sidebar">
    <div class="brand">
      <div class="mark">SG</div>
      <div>
        <div class="brand-title">SonarGrid</div>
        <div class="brand-sub">NMS Console</div>
      </div>
    </div>
    <nav class="nav">
      <a href="#dashboard">Dashboard</a>
      <a href="#devices">Devices</a>
      <a href="#topology">Topology</a>
      <a href="#jobs">Jobs</a>
      <a href="#settings">Settings</a>
    </nav>
  </aside>
  <main class="main">
    <header class="topbar">
      <div>
        <h1>SonarGrid NMS</h1>
        <div class="muted">Information collection and inferred topology</div>
      </div>
      <div class="actions">
        <span class="pill {{ 'warn' if frozen else 'ok' }}">Topology {{ "paused" if frozen else "live" }}</span>
        <a class="button secondary" href="{{ url_for('export_devices') }}">Devices CSV</a>
        <a class="button secondary" href="{{ url_for('export_observations') }}">Observations CSV</a>
      </div>
    </header>
    <section class="content">
      <section id="dashboard" class="stats">
        <div class="stat"><div class="stat-label">Devices</div><div class="stat-value">{{ summary.devices }}</div></div>
        <div class="stat"><div class="stat-label">Inactive</div><div class="stat-value">{{ summary.inactive }}</div></div>
        <div class="stat"><div class="stat-label">Observations</div><div class="stat-value">{{ summary.observations }}</div></div>
        <div class="stat"><div class="stat-label">Successful Jobs</div><div class="stat-value">{{ summary.success_runs }}</div></div>
        <div class="stat"><div class="stat-label">Failed Jobs</div><div class="stat-value">{{ summary.failed_runs }}</div></div>
        <div class="stat"><div class="stat-label">Topology</div><div class="stat-value">{{ summary.topology_nodes }}/{{ summary.topology_edges }}</div></div>
      </section>

      <section id="settings" class="grid">
        <div class="panel">
          <div class="panel-head"><h2>Collection Jobs</h2></div>
          <div class="panel-body forms">
            <form class="inline" method="post" action="{{ url_for('add_job') }}">
              <label>Name <input name="name" value="Local discovery"></label>
              <label>CIDR <input name="target" value="127.0.0.0/30"></label>
              <label>Interval <input name="interval_seconds" value="3600" type="number"></label>
              <button>Discovery</button>
            </form>
            <form class="inline" method="post" action="{{ url_for('add_collect_job') }}">
              <label>Name <input name="name" value="Collect all devices"></label>
              <label>Target <input name="target" value="all"></label>
              <label>Interval <input name="interval_seconds" value="300" type="number"></label>
              <button>Collect</button>
            </form>
            <form class="inline" method="post" action="{{ url_for('add_topology_job') }}">
              <label>Name <input name="name" value="Rebuild topology"></label>
              <label>Interval <input name="interval_seconds" value="300" type="number"></label>
              <span></span>
              <button>Topology</button>
            </form>
          </div>
        </div>
        <div class="panel">
          <div class="panel-head">
            <h2>Settings</h2>
            <span class="pill {{ 'ok' if snmp_configured else 'warn' }}">SNMP {{ "set" if snmp_configured else "unset" }}</span>
          </div>
          <div class="panel-body forms">
            <form class="compact" method="post" action="{{ url_for('save_snmp_settings') }}">
              <label style="flex:1 1 220px;">SNMP v2c community
                <input name="community" type="password" placeholder="{{ 'configured' if snmp_configured else 'not configured' }}">
              </label>
              <button>Save</button>
            </form>
            <div class="actions">
              <form method="post" action="{{ url_for('rebuild_topology_now') }}"><button class="secondary">Rebuild topology</button></form>
              <form method="post" action="{{ url_for('toggle_topology_freeze') }}">
                <input type="hidden" name="freeze" value="{{ '0' if frozen else '1' }}">
                <button class="{{ 'secondary' if frozen else 'warning' }}">{{ "Resume topology" if frozen else "Pause topology" }}</button>
              </form>
              <span class="pill {{ 'warn' if frozen else 'ok' }}">Freeze {{ "on" if frozen else "off" }}</span>
            </div>
          </div>
        </div>
      </section>

      <section id="devices" class="panel">
        <div class="panel-head"><h2>Devices</h2><span class="muted">{{ summary.devices }} total</span></div>
        <div class="table-wrap">
          <table>
            <tr><th>IP</th><th>Hostname</th><th>Type</th><th>Confidence</th><th>Source</th><th>Last Seen</th><th>State</th></tr>
            {% for d in devices %}
            <tr>
              <td class="mono">{{ d.ip }}</td>
              <td>{{ d.hostname or "" }}</td>
              <td><span class="pill">{{ d.device_type }}</span></td>
              <td>{{ d.detection_confidence }}</td>
              <td>{{ d.detection_source }}</td>
              <td class="mono">{{ d.last_seen_at or "" }}</td>
              <td>{% if d.inactive_at %}<span class="pill warn">inactive</span>{% else %}<span class="pill ok">collected</span>{% endif %}</td>
            </tr>
            {% endfor %}
          </table>
        </div>
      </section>

      <section id="topology" class="split">
        <div class="panel">
          <div class="panel-head"><h2>Topology Nodes</h2><span class="muted">{{ summary.topology_nodes }} nodes</span></div>
          <div class="table-wrap">
            <table>
              <tr><th>Node</th><th>Type</th><th>Status</th><th>Confidence</th><th>Updated</th></tr>
              {% for n in topology_nodes %}
              <tr><td>{{ n.label }}</td><td>{{ n.node_type }}</td><td><span class="pill {{ 'ok' if n.status == 'collected' else 'warn' }}">{{ n.status }}</span></td><td>{{ n.confidence }}</td><td class="mono">{{ n.updated_at }}</td></tr>
              {% endfor %}
            </table>
          </div>
        </div>
        <div class="panel">
          <div class="panel-head"><h2>Topology Edges</h2><span class="muted">{{ summary.topology_edges }} edges</span></div>
          <div class="table-wrap">
            <table>
              <tr><th>Source</th><th>Target</th><th>Relation</th><th>Confidence</th><th>Notes</th></tr>
              {% for e in topology_edges %}
              <tr><td>{{ e.source_label }}</td><td>{{ e.target_label }}</td><td>{{ e.relation }}</td><td>{{ e.confidence }}</td><td class="truncate">{{ e.notes }}</td></tr>
              {% endfor %}
            </table>
          </div>
        </div>
      </section>

      <section id="jobs" class="panel">
        <div class="panel-head"><h2>Jobs</h2></div>
        <div class="table-wrap">
          <table>
            <tr><th>Name</th><th>Type</th><th>Target</th><th>Next Run</th><th>Last Success</th><th>Failures</th><th>Last Error</th></tr>
            {% for j in jobs %}
            <tr><td>{{ j.name }}</td><td>{{ j.job_type }}</td><td class="mono">{{ j.target }}</td><td class="mono">{{ j.next_run_at or "" }}</td><td class="mono">{{ j.last_success_at or "" }}</td><td>{{ j.consecutive_failures }}</td><td class="truncate">{{ j.last_error }}</td></tr>
            {% endfor %}
          </table>
        </div>
      </section>

      <section class="split">
        <div class="panel">
          <div class="panel-head"><h2>Recent Job Runs</h2></div>
          <div class="table-wrap">
            <table>
              <tr><th>Type</th><th>Target</th><th>Status</th><th>Started</th><th>Error</th></tr>
              {% for r in runs %}
              <tr><td>{{ r.job_type }}</td><td class="mono">{{ r.target }}</td><td><span class="pill {{ 'ok' if r.status == 'success' else 'bad' }}">{{ r.status }}</span></td><td class="mono">{{ r.started_at }}</td><td class="truncate">{{ r.error }}</td></tr>
              {% endfor %}
            </table>
          </div>
        </div>
        <div class="panel">
          <div class="panel-head"><h2>Notifications</h2></div>
          <div class="table-wrap">
            <table>
              <tr><th>Channel</th><th>Status</th><th>Sent</th><th>Message</th><th>Error</th></tr>
              {% for n in notifications %}
              <tr><td>{{ n.channel }}</td><td><span class="pill {{ 'ok' if n.status == 'sent' else 'warn' }}">{{ n.status }}</span></td><td class="mono">{{ n.sent_at }}</td><td class="truncate">{{ n.message }}</td><td class="truncate">{{ n.error }}</td></tr>
              {% endfor %}
            </table>
          </div>
        </div>
      </section>
    </section>
  </main>
</div>
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
