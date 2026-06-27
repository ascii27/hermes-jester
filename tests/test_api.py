from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from jester import db, keys_repo
from jester.app import create_app
from jester.config import Settings

NOTE_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


@pytest.fixture
def env(tmp_path):
    db_file = str(tmp_path / "jester.db")
    c = db.connect(db_file)
    db.init_db(c)
    _, admin = keys_repo.create_key(c, "admin", "admin")
    _, write = keys_repo.create_key(c, "sender", "write")
    _, read = keys_repo.create_key(c, "hermes", "read")
    c.close()
    app = create_app(Settings(db_path=db_file))
    return SimpleNamespace(client=TestClient(app), admin=admin, write=write, read=read)


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _register_note(env):
    return env.client.post(
        "/api/types", headers=hdr(env.admin), json={"name": "note", "schema": NOTE_SCHEMA}
    )


# --- auth ---

def test_health_needs_no_auth(env):
    assert env.client.get("/health").status_code == 200


def test_missing_token_is_401(env):
    assert env.client.get("/api/types").status_code == 401


def test_bad_token_is_401(env):
    assert env.client.get("/api/types", headers=hdr("jstr_nope")).status_code == 401


def test_wrong_scope_is_403(env):
    r = env.client.post(
        "/api/types", headers=hdr(env.read), json={"name": "note", "schema": NOTE_SCHEMA}
    )
    assert r.status_code == 403


def test_revoked_token_is_401(env, tmp_path):
    c = db.connect(str(tmp_path / "jester.db"))
    write_id = next(k["id"] for k in keys_repo.list_keys(c) if k["name"] == "sender")
    keys_repo.revoke_key(c, write_id)
    c.close()
    _register_note(env)
    r = env.client.post("/api/item/note", headers=hdr(env.write), json={"text": "x"})
    assert r.status_code == 401


# --- discovery ---

def test_discover_requires_auth(env):
    assert env.client.get("/api/discover").status_code == 401


def test_discover_lists_registered_types(env):
    _register_note(env)
    r = env.client.get("/api/discover", headers=hdr(env.read))
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "hermes-jester"
    assert "/api/items/ack" in body["polling"]["ack"]
    names = [t["name"] for t in body["types"]]
    assert "note" in names
    note = next(t for t in body["types"] if t["name"] == "note")
    assert note["content_schema"] == NOTE_SCHEMA
    assert note["example_content"] == {"text": "string"}
    assert note["fetch"]["unread"].endswith("/api/item/note?unread=true")


# --- types (REST) ---

def test_register_and_get_type(env):
    r = _register_note(env)
    assert r.status_code == 201, r.text
    assert r.json()["schema"] == NOTE_SCHEMA
    g = env.client.get("/api/types/note", headers=hdr(env.read))
    assert g.status_code == 200
    assert g.json()["name"] == "note"


def test_register_invalid_schema_is_422(env):
    r = env.client.post(
        "/api/types", headers=hdr(env.admin), json={"name": "bad", "schema": {"type": 123}}
    )
    assert r.status_code == 422


def test_duplicate_type_is_409(env):
    _register_note(env)
    assert _register_note(env).status_code == 409


def test_update_type(env):
    _register_note(env)
    new = {"type": "object", "properties": {"body": {"type": "string"}}}
    r = env.client.put(
        "/api/types/note", headers=hdr(env.admin), json={"description": "d", "schema": new}
    )
    assert r.status_code == 200
    assert r.json()["schema"] == new


def test_delete_type(env):
    _register_note(env)
    r = env.client.delete("/api/types/note", headers=hdr(env.admin))
    assert r.status_code == 200
    assert env.client.get("/api/types/note", headers=hdr(env.read)).status_code == 404


def test_delete_type_with_items_is_409(env):
    _register_note(env)
    env.client.post("/api/item/note", headers=hdr(env.write), json={"text": "a"})
    r = env.client.delete("/api/types/note", headers=hdr(env.admin))
    assert r.status_code == 409


# --- submit (type in path; body is the payload) ---

def test_submit_valid_item(env):
    _register_note(env)
    r = env.client.post("/api/item/note", headers=hdr(env.write), json={"text": "hi"})
    assert r.status_code == 201, r.text
    assert r.json()["id"] and r.json()["created_at"]
    # the stored item's payload is exactly the posted body
    feed = env.client.get("/api/items", headers=hdr(env.read)).json()
    assert feed[0]["payload"] == {"text": "hi"}


def test_submit_invalid_payload_is_422(env):
    _register_note(env)
    r = env.client.post("/api/item/note", headers=hdr(env.write), json={"nope": 1})
    assert r.status_code == 422


def test_submit_unknown_type_is_404(env):
    r = env.client.post("/api/item/ghost", headers=hdr(env.write), json={"x": 1})
    assert r.status_code == 404


# --- consume ---

def test_list_items_by_type(env):
    _register_note(env)
    env.client.post("/api/item/note", headers=hdr(env.write), json={"text": "a"})
    r = env.client.get("/api/item/note", headers=hdr(env.read))
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_items_unknown_type_is_404(env):
    assert env.client.get("/api/item/ghost", headers=hdr(env.read)).status_code == 404


def test_cross_type_feed(env):
    _register_note(env)
    env.client.post("/api/types", headers=hdr(env.admin), json={"name": "link", "schema": {"type": "object"}})
    env.client.post("/api/item/note", headers=hdr(env.write), json={"text": "a"})
    env.client.post("/api/item/link", headers=hdr(env.write), json={"url": "x"})
    feed = env.client.get("/api/items", headers=hdr(env.read)).json()
    assert len(feed) == 2
    only_note = env.client.get("/api/items", headers=hdr(env.read), params={"type": "note"}).json()
    assert len(only_note) == 1


def test_get_single_item(env):
    _register_note(env)
    sid = env.client.post("/api/item/note", headers=hdr(env.write), json={"text": "a"}).json()["id"]
    r = env.client.get(f"/api/item/note/{sid}", headers=hdr(env.read))
    assert r.status_code == 200
    assert r.json()["id"] == sid


def test_patch_marks_read_and_unread(env):
    _register_note(env)
    sid = env.client.post("/api/item/note", headers=hdr(env.write), json={"text": "a"}).json()["id"]
    r = env.client.patch(f"/api/item/note/{sid}", headers=hdr(env.read), json={"read": True})
    assert r.status_code == 200
    assert r.json()["read_at"] is not None
    assert env.client.get("/api/item/note", headers=hdr(env.read)).json() == []
    env.client.patch(f"/api/item/note/{sid}", headers=hdr(env.read), json={"read": False})
    assert len(env.client.get("/api/item/note", headers=hdr(env.read)).json()) == 1


def test_patch_unknown_item_is_404(env):
    _register_note(env)
    r = env.client.patch("/api/item/note/nope", headers=hdr(env.read), json={"read": True})
    assert r.status_code == 404


def test_bulk_ack(env):
    _register_note(env)
    ids = [
        env.client.post("/api/item/note", headers=hdr(env.write), json={"text": str(n)}).json()["id"]
        for n in range(2)
    ]
    r = env.client.post("/api/items/ack", headers=hdr(env.read), json={"ids": ids})
    assert r.status_code == 200 and r.json()["acked"] == 2
    assert env.client.get("/api/items", headers=hdr(env.read)).json() == []


def test_delete_item(env):
    _register_note(env)
    sid = env.client.post("/api/item/note", headers=hdr(env.write), json={"text": "a"}).json()["id"]
    r = env.client.delete(f"/api/item/note/{sid}", headers=hdr(env.admin))
    assert r.status_code == 200
    assert env.client.get(f"/api/item/note/{sid}", headers=hdr(env.read)).status_code == 404


def test_poll_limit(env):
    _register_note(env)
    for n in range(3):
        env.client.post("/api/item/note", headers=hdr(env.write), json={"text": str(n)})
    assert len(env.client.get("/api/items", headers=hdr(env.read), params={"limit": 2}).json()) == 2
