PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL UNIQUE,
    hostname TEXT,
    mac TEXT,
    device_type TEXT NOT NULL DEFAULT 'unknown',
    detection_confidence TEXT NOT NULL DEFAULT 'low',
    detection_source TEXT NOT NULL DEFAULT 'unknown',
    detection_notes TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT,
    inactive_at TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_type_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL REFERENCES devices(id),
    device_type TEXT NOT NULL,
    confidence TEXT NOT NULL,
    source TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    detected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    job_type TEXT NOT NULL,
    target TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 300,
    enabled INTEGER NOT NULL DEFAULT 1,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_run_at TEXT,
    last_success_at TEXT,
    last_error TEXT NOT NULL DEFAULT '',
    next_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES collection_jobs(id),
    job_type TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER REFERENCES devices(id),
    source TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topology_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER REFERENCES devices(id),
    label TEXT NOT NULL,
    node_type TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',
    source TEXT NOT NULL DEFAULT 'inventory',
    updated_at TEXT NOT NULL,
    UNIQUE(device_id)
);

CREATE TABLE IF NOT EXISTS topology_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id INTEGER NOT NULL REFERENCES topology_nodes(id),
    target_node_id INTEGER NOT NULL REFERENCES topology_nodes(id),
    relation TEXT NOT NULL,
    confidence TEXT NOT NULL,
    source TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE(source_node_id, target_node_id, relation)
);

CREATE TABLE IF NOT EXISTS topology_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_run_id INTEGER REFERENCES job_runs(id),
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_devices_last_seen_at ON devices(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_job_runs_started_at ON job_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_observations_observed_at ON observations(observed_at);
CREATE INDEX IF NOT EXISTS idx_notifications_sent_at ON notifications(sent_at);
CREATE INDEX IF NOT EXISTS idx_topology_nodes_device_id ON topology_nodes(device_id);
