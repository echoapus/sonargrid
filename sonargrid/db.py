from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("sonargrid.db")
SCHEMA_PATH = Path("schema.sql")


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path | str = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        ensure_columns(conn)


def ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(collection_jobs)").fetchall()
    }
    additions = {
        "consecutive_failures": "ALTER TABLE collection_jobs ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0",
        "last_success_at": "ALTER TABLE collection_jobs ADD COLUMN last_success_at TEXT",
        "last_error": "ALTER TABLE collection_jobs ADD COLUMN last_error TEXT NOT NULL DEFAULT ''",
    }
    for column, sql in additions.items():
        if column not in columns:
            conn.execute(sql)
