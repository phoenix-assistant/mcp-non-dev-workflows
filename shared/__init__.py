"""Shared database and audit utilities for all MCP servers."""

import sqlite3
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def get_db(db_path: str) -> sqlite3.Connection:
    """Get or create a SQLite connection with WAL mode."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def generate_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_audit(conn: sqlite3.Connection, action: str, entity_type: str,
              entity_id: str, actor: str, details: dict | None = None):
    """Append-only audit log entry."""
    conn.execute("""
        INSERT INTO audit_log (id, timestamp, action, entity_type, entity_id, actor, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (generate_id(), now_iso(), action, entity_type, entity_id, actor, json.dumps(details or {})))
    conn.commit()
