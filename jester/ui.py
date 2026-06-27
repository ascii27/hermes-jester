"""Server-rendered management UI (Google-auth session protected)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from . import items_repo, keys_repo, types_repo
from .auth_ui import require_user
from .deps import get_conn
from .errors import JesterError

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

router = APIRouter()


def _ctx(request: Request, **kw) -> dict:
    return {"user": request.session.get("user"), **kw}


def render(request: Request, name: str, status_code: int = 200, **kw):
    return templates.TemplateResponse(request, name, _ctx(request, **kw), status_code=status_code)


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
    return render(
        request,
        "dashboard.html",
        counts=counts,
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
    return render(request, "types.html", types=types_repo.list_types(conn))


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
        return render(
            request,
            "types.html",
            status_code=400,
            types=types_repo.list_types(conn),
            error=error,
            form={"name": name, "description": description, "schema": schema_text},
        )
    return RedirectResponse(url="/ui/types", status_code=303)


@router.get("/ui/types/{name}/edit")
def edit_type_page(
    name: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    type_def = types_repo.get_type(conn, name)
    return render(
        request,
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
        return render(
            request,
            "type_edit.html",
            status_code=400,
            type_def=types_repo.get_type(conn, name),
            schema_text=schema_text,
            error=error,
        )
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
    items = items_repo.query_items(
        conn, unread=unread, type=type or None, limit=500
    )
    return render(
        request,
        "items.html",
        items=items,
        types=types_repo.list_types(conn),
        selected_type=type or "",
        state=state,
    )


@router.get("/ui/items/{item_id}")
def item_detail(
    item_id: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    item = items_repo.get_item(conn, item_id)
    return render(
        request,
        "item_detail.html",
        item=item,
        payload_text=json.dumps(item["payload"], indent=2) if item else "",
        metadata_text=json.dumps(item["metadata"], indent=2) if item else "",
    )


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
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    items_repo.delete_item(conn, item_id)
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
    return render(
        request,
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
    conn: sqlite3.Connection = Depends(get_conn),
    _user: dict = Depends(require_user),
):
    keys_repo.revoke_key(conn, key_id)
    return RedirectResponse(url="/ui/keys", status_code=303)
