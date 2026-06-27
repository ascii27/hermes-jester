"""Programmatic API routes (bearer-key authenticated)."""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from . import items_repo, types_repo
from .auth_api import require_scope
from .deps import get_conn
from .models import AckRequest, ItemSubmit, TypeCreate, TypeUpdate

router = APIRouter(prefix="/api")

MAX_LIMIT = 500


# --- types ---

@router.post("/types", status_code=201)
def create_type(
    body: TypeCreate,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("admin")),
):
    return types_repo.register_type(conn, body.name, body.description, body.json_schema)


@router.get("/types")
def list_types(
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
):
    return types_repo.list_types(conn)


@router.get("/types/{name}")
def get_type(
    name: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
):
    type_def = types_repo.get_type(conn, name)
    if type_def is None:
        raise HTTPException(status_code=404, detail=f"type {name!r} not found")
    return type_def


@router.put("/types/{name}")
def update_type(
    name: str,
    body: TypeUpdate,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("admin")),
):
    return types_repo.update_type(
        conn, name, description=body.description, schema=body.json_schema
    )


# --- submit ---

@router.post("/items", status_code=201)
def submit_item(
    body: ItemSubmit,
    conn: sqlite3.Connection = Depends(get_conn),
    key: dict = Depends(require_scope("write")),
):
    item = items_repo.submit(
        conn, body.type, body.payload, metadata=body.metadata, source=key["name"]
    )
    return {"id": item["id"], "created_at": item["created_at"]}


@router.get("/submit", status_code=201)
def submit_item_get(
    conn: sqlite3.Connection = Depends(get_conn),
    key: dict = Depends(require_scope("write")),
    type: str = Query(...),
    payload: str = Query(..., description="JSON-encoded payload"),
    metadata: str | None = Query(default=None, description="JSON-encoded metadata"),
):
    """Submission for sources that can only issue GET requests. `payload` and
    `metadata` are JSON-encoded query params."""
    try:
        payload_obj = json.loads(payload)
        metadata_obj = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    item = items_repo.submit(
        conn, type, payload_obj, metadata=metadata_obj, source=key["name"]
    )
    return {"id": item["id"], "created_at": item["created_at"]}


# --- consume ---

@router.get("/items")
def list_items(
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
    unread: bool = Query(default=True),
    type: str | None = Query(default=None),
    since: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
):
    return items_repo.query_items(
        conn, unread=unread, type=type, since=since, limit=limit
    )


@router.get("/items/{item_id}")
def get_item(
    item_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
):
    item = items_repo.get_item(conn, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return item


@router.post("/items/ack")
def ack_items(
    body: AckRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
):
    return {"acked": items_repo.ack(conn, body.ids)}
