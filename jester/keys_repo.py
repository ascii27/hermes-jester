"""Self-managed API keys: long-lived bearer tokens, stored only as a hash.

Scopes:
  admin  - manage types and keys (implies write + read)
  write  - submit items
  read   - poll and ack items
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid

from . import clock
from .errors import NotFoundError

VALID_SCOPES = ("read", "write", "admin")
TOKEN_PREFIX = "jstr_"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_key(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "token_hash": row["token_hash"],
        "scope": row["scope"],
        "created_at": row["created_at"],
        "revoked_at": row["revoked_at"],
    }


def scope_allows(have: str, need: str) -> bool:
    """Does a key with scope `have` satisfy a requirement for scope `need`?"""
    if have == "admin":
        return True
    return have == need


def create_key(conn: sqlite3.Connection, name: str, scope: str) -> tuple[dict, str]:
    """Create a key and return (record, plaintext_token). The plaintext is shown
    exactly once here and never persisted."""
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope must be one of {VALID_SCOPES}, got {scope!r}")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    key_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO api_keys (id, name, token_hash, scope, created_at, revoked_at) "
        "VALUES (?, ?, ?, ?, ?, NULL)",
        (key_id, name, _hash_token(token), scope, clock.now()),
    )
    conn.commit()
    return get_key(conn, key_id), token


def get_key(conn: sqlite3.Connection, key_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    return _row_to_key(row) if row else None


def list_keys(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM api_keys ORDER BY created_at DESC").fetchall()
    return [_row_to_key(r) for r in rows]


def authenticate(conn: sqlite3.Connection, token: str) -> dict | None:
    """Resolve a plaintext token to an active key record, or None."""
    if not token:
        return None
    row = conn.execute(
        "SELECT * FROM api_keys WHERE token_hash = ? AND revoked_at IS NULL",
        (_hash_token(token),),
    ).fetchone()
    return _row_to_key(row) if row else None


def revoke_key(conn: sqlite3.Connection, key_id: str) -> dict:
    if get_key(conn, key_id) is None:
        raise NotFoundError(f"key {key_id!r} not found")
    conn.execute(
        "UPDATE api_keys SET revoked_at = ? WHERE id = ?",
        (clock.now(), key_id),
    )
    conn.commit()
    return get_key(conn, key_id)
