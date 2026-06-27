"""Programmatic REST API (bearer-key authenticated).

Type definitions are a REST resource under /api/types. Items are addressed by
type in the path (/api/item/{type}); a cross-type feed lives at /api/items for
hermes's cron.
"""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from . import items_repo, types_repo
from .auth_api import require_scope
from .deps import get_conn
from .models import AckRequest, ItemBody, ItemPatch, TypeCreate, TypeUpdate

router = APIRouter(prefix="/api")

MAX_LIMIT = 500


def _require_type(conn: sqlite3.Connection, type: str) -> dict:
    type_def = types_repo.get_type(conn, type)
    if type_def is None:
        raise HTTPException(status_code=404, detail=f"type {type!r} not found")
    return type_def


# --- types (REST resource) ---

@router.get("/types")
def list_types(
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
):
    return types_repo.list_types(conn)


@router.post("/types", status_code=201)
def create_type(
    body: TypeCreate,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("admin")),
):
    return types_repo.register_type(conn, body.name, body.description, body.json_schema)


@router.get("/types/{type}")
def get_type(
    type: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
):
    return _require_type(conn, type)


@router.put("/types/{type}")
def update_type(
    type: str,
    body: TypeUpdate,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("admin")),
):
    return types_repo.update_type(
        conn, type, description=body.description, schema=body.json_schema
    )


@router.delete("/types/{type}")
def delete_type(
    type: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("admin")),
):
    types_repo.delete_type(conn, type)
    return {"deleted": type}


# --- submit (type in path) ---

@router.post("/item/{type}", status_code=201)
def submit_item(
    type: str,
    body: ItemBody,
    conn: sqlite3.Connection = Depends(get_conn),
    key: dict = Depends(require_scope("write")),
):
    item = items_repo.submit(
        conn, type, body.payload, metadata=body.metadata, source=key["name"]
    )
    return {"id": item["id"], "created_at": item["created_at"]}


@router.get("/submit/{type}", status_code=201)
def submit_item_get(
    type: str,
    conn: sqlite3.Connection = Depends(get_conn),
    key: dict = Depends(require_scope("write")),
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


# --- consume: cross-type feed (for the cron) ---

@router.get("/items")
def list_items(
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
    unread: bool = Query(default=True),
    type: str | None = Query(default=None),
    since: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
):
    return items_repo.query_items(conn, unread=unread, type=type, since=since, limit=limit)


@router.post("/items/ack")
def ack_items(
    body: AckRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
):
    return {"acked": items_repo.ack(conn, body.ids)}


# --- consume: per-type ---

@router.get("/item/{type}")
def list_items_of_type(
    type: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
    unread: bool = Query(default=True),
    since: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
):
    _require_type(conn, type)
    return items_repo.query_items(conn, unread=unread, type=type, since=since, limit=limit)


@router.get("/item/{type}/{item_id}")
def get_item(
    type: str,
    item_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
):
    item = items_repo.get_item(conn, item_id)
    if item is None or item["type"] != type:
        raise HTTPException(status_code=404, detail="item not found")
    return item


@router.patch("/item/{type}/{item_id}")
def patch_item(
    type: str,
    item_id: str,
    body: ItemPatch,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("read")),
):
    existing = items_repo.get_item(conn, item_id)
    if existing is None or existing["type"] != type:
        raise HTTPException(status_code=404, detail="item not found")
    return items_repo.set_read(conn, item_id, body.read)


@router.delete("/item/{type}/{item_id}")
def delete_item(
    type: str,
    item_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _key: dict = Depends(require_scope("admin")),
):
    existing = items_repo.get_item(conn, item_id)
    if existing is None or existing["type"] != type:
        raise HTTPException(status_code=404, detail="item not found")
    items_repo.delete_item(conn, item_id)
    return {"deleted": item_id}
