"""Registered data types: each carries a JSON Schema used to validate item payloads."""

from __future__ import annotations

import json
import sqlite3

import jsonschema
from jsonschema.exceptions import SchemaError
from jsonschema.validators import Draft202012Validator

from . import clock
from .errors import ConflictError, NotFoundError, PayloadInvalidError, SchemaInvalidError


def _row_to_type(row: sqlite3.Row) -> dict:
    return {
        "name": row["name"],
        "description": row["description"],
        "schema": json.loads(row["schema"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _check_schema(schema: dict) -> None:
    """Ensure `schema` is itself a valid JSON Schema."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SchemaInvalidError(str(exc)) from exc


def register_type(conn: sqlite3.Connection, name: str, description: str, schema: dict) -> dict:
    _check_schema(schema)
    ts = clock.now()
    try:
        conn.execute(
            "INSERT INTO types (name, description, schema, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, description or "", json.dumps(schema), ts, ts),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ConflictError(f"type {name!r} already exists") from exc
    return get_type(conn, name)


def get_type(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute("SELECT * FROM types WHERE name = ?", (name,)).fetchone()
    return _row_to_type(row) if row else None


def list_types(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM types ORDER BY name").fetchall()
    return [_row_to_type(r) for r in rows]


def update_type(
    conn: sqlite3.Connection,
    name: str,
    description: str | None = None,
    schema: dict | None = None,
) -> dict:
    existing = get_type(conn, name)
    if existing is None:
        raise NotFoundError(f"type {name!r} not found")
    if schema is not None:
        _check_schema(schema)
    new_description = existing["description"] if description is None else description
    new_schema = existing["schema"] if schema is None else schema
    conn.execute(
        "UPDATE types SET description = ?, schema = ?, updated_at = ? WHERE name = ?",
        (new_description, json.dumps(new_schema), clock.now(), name),
    )
    conn.commit()
    return get_type(conn, name)


def validate_payload(schema: dict, payload: object) -> None:
    """Validate an item payload against a type's JSON Schema; raise on mismatch."""
    try:
        jsonschema.validate(instance=payload, schema=schema)
    except jsonschema.ValidationError as exc:
        raise PayloadInvalidError(exc.message) from exc
