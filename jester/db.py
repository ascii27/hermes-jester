"""SQLite connection management and idempotent schema setup.

The database is used as a flexible KV store: `payload` and `metadata` are opaque
JSON documents stored as TEXT, while a few promoted columns (type, source,
created_at, read_at) make the queue queries fast.
"""

from __future__ import annotations

import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS types (
    name        TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    schema      TEXT NOT NULL,            -- JSON Schema for an item's payload
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL REFERENCES types(name),
    payload     TEXT NOT NULL,            -- the posted JSON body (validated against type schema)
    source      TEXT NOT NULL DEFAULT '',    -- name of the API key that submitted it
    created_at  TEXT NOT NULL,
    read_at     TEXT                          -- NULL until acked
);

CREATE INDEX IF NOT EXISTS idx_items_unread  ON items(read_at, created_at);
CREATE INDEX IF NOT EXISTS idx_items_type    ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_created ON items(created_at);

CREATE TABLE IF NOT EXISTS api_keys (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    token_hash  TEXT NOT NULL UNIQUE,     -- sha256 of the plaintext token
    scope       TEXT NOT NULL,            -- 'write' | 'read' | 'admin'
    created_at  TEXT NOT NULL,
    revoked_at  TEXT                       -- NULL while active
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with sane defaults and row access by column name."""
    if db_path != ":memory:":
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they don't exist. Safe to call repeatedly."""
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Converge an existing database to the current schema."""
    # Legacy installs had an items.metadata column; drop it (the envelope idea
    # was removed — the posted body is the payload).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    if "metadata" in cols:
        try:
            conn.execute("ALTER TABLE items DROP COLUMN metadata")
        except sqlite3.OperationalError:
            pass  # older SQLite without DROP COLUMN: leave the unused column
