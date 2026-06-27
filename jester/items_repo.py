"""The queue itself: submit items, poll unread, ack.

An item is an envelope: a validated `payload` (the data), a free-form `metadata`
object (sender-supplied context), and system fields the service stamps on.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from . import clock, types_repo
from .errors import NotFoundError


def _row_to_item(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "type": row["type"],
        "payload": json.loads(row["payload"]),
        "source": row["source"],
        "created_at": row["created_at"],
        "read_at": row["read_at"],
    }


def submit(
    conn: sqlite3.Connection,
    type: str,
    payload: object,
    source: str = "",
) -> dict:
    """Validate the posted body against the type's schema and enqueue. Raises if
    the type is unknown or the body doesn't match the schema."""
    type_def = types_repo.get_type(conn, type)
    if type_def is None:
        raise NotFoundError(f"type {type!r} is not registered")
    types_repo.validate_payload(type_def["schema"], payload)

    item_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO items (id, type, payload, source, created_at, read_at) "
        "VALUES (?, ?, ?, ?, ?, NULL)",
        (item_id, type, json.dumps(payload), source, clock.now()),
    )
    conn.commit()
    return get_item(conn, item_id)


def get_item(conn: sqlite3.Connection, item_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def query_items(
    conn: sqlite3.Connection,
    unread: bool = True,
    type: str | None = None,
    since: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return items oldest-first. Defaults to unread only."""
    clauses = []
    params: list = []
    if unread:
        clauses.append("read_at IS NULL")
    if type is not None:
        clauses.append("type = ?")
        params.append(type)
    if since is not None:
        clauses.append("created_at > ?")
        params.append(since)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM items {where} ORDER BY created_at ASC, id ASC LIMIT ?",
        params,
    ).fetchall()
    return [_row_to_item(r) for r in rows]


def ack(conn: sqlite3.Connection, ids: list[str]) -> int:
    """Mark the given items read. Returns the number newly marked (already-read ignored)."""
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"UPDATE items SET read_at = ? WHERE read_at IS NULL AND id IN ({placeholders})",
        [clock.now(), *ids],
    )
    conn.commit()
    return cur.rowcount


def set_read(conn: sqlite3.Connection, item_id: str, read: bool) -> dict | None:
    """Mark a single item read (read=True) or unread (read=False). Returns the
    updated item, or None if it doesn't exist."""
    if get_item(conn, item_id) is None:
        return None
    conn.execute(
        "UPDATE items SET read_at = ? WHERE id = ?",
        (clock.now() if read else None, item_id),
    )
    conn.commit()
    return get_item(conn, item_id)


def mark_unread(conn: sqlite3.Connection, ids: list[str]) -> int:
    """Reset items to unread. Returns number affected."""
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"UPDATE items SET read_at = NULL WHERE id IN ({placeholders})",
        list(ids),
    )
    conn.commit()
    return cur.rowcount


def delete_item(conn: sqlite3.Connection, item_id: str) -> bool:
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    return cur.rowcount > 0


def counts(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    unread = conn.execute("SELECT COUNT(*) FROM items WHERE read_at IS NULL").fetchone()[0]
    return {"total": total, "unread": unread}
