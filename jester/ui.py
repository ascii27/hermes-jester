"""Server-rendered management UI (Google-auth session protected)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from . import items_repo, keys_repo, types_repo
from .auth_ui import require_user
from .deps import get_conn
from .errors import JesterError
from .examples import example_payload

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

router = APIRouter()

_TS_FORMATS = ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value: str) -> datetime | None:
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _ago(value: str) -> str:
    """Render an ISO timestamp as a short relative string (e.g. '5m ago')."""
    dt = _parse_ts(value)
    if dt is None:
        return value or ""
    mins = (datetime.now(timezone.utc) - dt).total_seconds() / 60
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{int(mins)}m ago"
    if mins < 1440:
        return f"{int(mins // 60)}h ago"
    return f"{int(mins // 1440)}d ago"


def _absdt(value: str) -> str:
    """Render an ISO timestamp as an absolute local-ish string for detail views."""
    dt = _parse_ts(value)
    if dt is None:
        return value or ""
    return dt.strftime("%b %-d, %Y, %-I:%M %p UTC")


templates.env.filters["ago"] = _ago
templates.env.filters["absdt"] = _absdt


def _ctx(request: Request, **kw) -> dict:
    return {"user": request.session.get("user"), **kw}


def render(request: Request, name: str, status_code: int = 200, **kw):
    return templates.TemplateResponse(request, name, _ctx(request, **kw), status_code=status_code)


def render_app(
    request: Request,
    conn: sqlite3.Connection,
    name: str,
    status_code: int = 200,
    **kw,
):
    """Render an authenticated page, injecting the nav unread badge and any
    pending flash message."""
    nav_unread = items_repo.counts(conn)["unread"]
    flash = request.session.pop("flash", None)
    # The route is auth-gated by require_user; ensure the app shell renders even
    # when the session cookie isn't the source of the user (e.g. dependency overrides).
    user = request.session.get("user") or {"email": ""}
    return render(
        request, name, status_code=status_code,
        user=user, nav_unread=nav_unread, flash=flash, **kw,
    )


# --- login (no auth) ---

@router.get("/login")
def login_page(request: Request):
    return render(request, "login.html")


# --- dashboard ---

@router.get("/")
def dashboard(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    counts = items_repo.counts(conn)
    # query_items returns oldest-first; reverse for a newest-first feed.
    recent = list(reversed(items_repo.query_items(conn, unread=False, limit=500)))[:6]
    return render_app(
        request,
        conn,
        "dashboard.html",
        counts=counts,
        recent=recent,
        types=types_repo.list_types(conn),
        key_count=len(keys_repo.list_keys(conn)),
    )


# --- types ---

@router.get("/ui/types")
def types_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    base_url = request.app.state.settings.base_url.rstrip("/")
    types = types_repo.list_types(conn)
    examples = {
        t["name"]: json.dumps(example_payload(t["schema"])) for t in types
    }
    return render_app(
        request, conn, "types.html", types=types, examples=examples, base_url=base_url
    )


@router.post("/ui/types")
def create_type(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
    name: str = Form(...),
    description: str = Form(""),
    schema_text: str = Form(..., alias="schema"),
):
    error = None
    try:
        schema_obj = json.loads(schema_text)
        types_repo.register_type(conn, name, description, schema_obj)
    except json.JSONDecodeError as exc:
        error = f"Schema is not valid JSON: {exc}"
    except JesterError as exc:
        error = str(exc)
    if error:
        return render_app(
            request,
            conn,
            "types.html",
            status_code=400,
            types=types_repo.list_types(conn),
            base_url=request.app.state.settings.base_url.rstrip("/"),
            examples={
                t["name"]: json.dumps(example_payload(t["schema"]))
                for t in types_repo.list_types(conn)
            },
            error=error,
            form={"name": name, "description": description, "schema": schema_text},
        )
    request.session["flash"] = f"Type “{name}” registered."
    return RedirectResponse(url="/ui/types", status_code=303)


@router.get("/ui/types/{name}/edit")
def edit_type_page(
    name: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    type_def = types_repo.get_type(conn, name)
    return render_app(
        request,
        conn,
        "type_edit.html",
        type_def=type_def,
        schema_text=json.dumps(type_def["schema"], indent=2),
    )


@router.post("/ui/types/{name}")
def update_type(
    name: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
    description: str = Form(""),
    schema_text: str = Form(..., alias="schema"),
):
    error = None
    try:
        types_repo.update_type(conn, name, description=description, schema=json.loads(schema_text))
    except json.JSONDecodeError as exc:
        error = f"Schema is not valid JSON: {exc}"
    except JesterError as exc:
        error = str(exc)
    if error:
        return render_app(
            request,
            conn,
            "type_edit.html",
            status_code=400,
            type_def=types_repo.get_type(conn, name),
            schema_text=schema_text,
            error=error,
        )
    request.session["flash"] = f"Type “{name}” saved."
    return RedirectResponse(url="/ui/types", status_code=303)


# --- items ---

@router.get("/ui/items")
def items_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
    type: str | None = None,
    state: str = "all",
):
    unread = state == "unread"
    # query_items returns oldest-first; reverse for a newest-first browse view.
    items = list(reversed(items_repo.query_items(
        conn, unread=unread, type=type or None, limit=500
    )))
    unread_here = sum(1 for i in items if not i["read_at"])
    return render_app(
        request,
        conn,
        "items.html",
        items=items,
        types=types_repo.list_types(conn),
        selected_type=type or "",
        state=state,
        unread_here=unread_here,
    )


@router.get("/ui/items/{item_id}")
def item_detail(
    item_id: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    item = items_repo.get_item(conn, item_id)
    return render_app(
        request,
        conn,
        "item_detail.html",
        item=item,
        payload_text=json.dumps(item["payload"], indent=2) if item else "",
    )


@router.post("/ui/items/bulk")
def bulk_items(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
    action: str = Form(...),
    ids: list[str] = Form(default=[]),
):
    if ids:
        if action == "ack":
            n = items_repo.ack(conn, ids)
            request.session["flash"] = f"Acked {n} item{'s' if n != 1 else ''}."
        elif action == "delete":
            n = sum(1 for i in ids if items_repo.delete_item(conn, i))
            request.session["flash"] = f"Deleted {n} item{'s' if n != 1 else ''}."
    return RedirectResponse(url="/ui/items", status_code=303)


@router.post("/ui/items/{item_id}/ack")
def ack_item(
    item_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    items_repo.ack(conn, [item_id])
    return RedirectResponse(url="/ui/items", status_code=303)


@router.post("/ui/items/{item_id}/unread")
def unread_item(
    item_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    items_repo.mark_unread(conn, [item_id])
    return RedirectResponse(url="/ui/items", status_code=303)


@router.post("/ui/items/{item_id}/delete")
def delete_item(
    item_id: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    items_repo.delete_item(conn, item_id)
    request.session["flash"] = "Item deleted."
    return RedirectResponse(url="/ui/items", status_code=303)


# --- keys ---

@router.get("/ui/keys")
def keys_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    new_token = request.session.pop("new_token", None)
    new_token_name = request.session.pop("new_token_name", None)
    return render_app(
        request,
        conn,
        "keys.html",
        keys=keys_repo.list_keys(conn),
        scopes=keys_repo.VALID_SCOPES,
        new_token=new_token,
        new_token_name=new_token_name,
    )


@router.post("/ui/keys")
def create_key(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
    name: str = Form(...),
    scope: str = Form(...),
):
    _record, token = keys_repo.create_key(conn, name, scope)
    request.session["new_token"] = token
    request.session["new_token_name"] = name
    return RedirectResponse(url="/ui/keys", status_code=303)


@router.post("/ui/keys/{key_id}/revoke")
def revoke_key(
    key_id: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    keys_repo.revoke_key(conn, key_id)
    request.session["flash"] = "Key revoked."
    return RedirectResponse(url="/ui/keys", status_code=303)
