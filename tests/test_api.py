import json
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


# --- auth ---

def test_health_needs_no_auth(env):
    assert env.client.get("/health").status_code == 200


def test_missing_token_is_401(env):
    assert env.client.get("/api/types").status_code == 401


def test_bad_token_is_401(env):
    assert env.client.get("/api/types", headers=hdr("jstr_nope")).status_code == 401


def test_wrong_scope_is_403(env):
    # read key cannot register a type (admin-only)
    r = env.client.post(
        "/api/types",
        headers=hdr(env.read),
        json={"name": "note", "description": "", "schema": NOTE_SCHEMA},
    )
    assert r.status_code == 403


def test_revoked_token_is_401(env, tmp_path):
    # revoke the write key out-of-band
    c = db.connect(str(tmp_path / "jester.db"))
    keys = keys_repo.list_keys(c)
    write_id = next(k["id"] for k in keys if k["name"] == "sender")
    keys_repo.revoke_key(c, write_id)
    c.close()
    r = env.client.post(
        "/api/items", headers=hdr(env.write), json={"type": "note", "payload": {"text": "x"}}
    )
    assert r.status_code == 401


# --- types ---

def test_register_and_get_type(env):
    r = env.client.post(
        "/api/types",
        headers=hdr(env.admin),
        json={"name": "note", "description": "A note", "schema": NOTE_SCHEMA},
    )
    assert r.status_code == 201, r.text
    assert r.json()["schema"] == NOTE_SCHEMA

    g = env.client.get("/api/types/note", headers=hdr(env.read))
    assert g.status_code == 200
    assert g.json()["name"] == "note"


def test_register_invalid_schema_is_422(env):
    r = env.client.post(
        "/api/types",
        headers=hdr(env.admin),
        json={"name": "bad", "schema": {"type": 123}},
    )
    assert r.status_code == 422


def test_duplicate_type_is_409(env):
    body = {"name": "note", "schema": NOTE_SCHEMA}
    env.client.post("/api/types", headers=hdr(env.admin), json=body)
    r = env.client.post("/api/types", headers=hdr(env.admin), json=body)
    assert r.status_code == 409


# --- submit & consume ---

def _register_note(env):
    env.client.post(
        "/api/types",
        headers=hdr(env.admin),
        json={"name": "note", "schema": NOTE_SCHEMA},
    )


def test_submit_valid_item(env):
    _register_note(env)
    r = env.client.post(
        "/api/items",
        headers=hdr(env.write),
        json={"type": "note", "payload": {"text": "hi"}, "metadata": {"k": "v"}},
    )
    assert r.status_code == 201, r.text
    assert r.json()["id"]
    assert r.json()["created_at"]


def test_submit_invalid_payload_is_422(env):
    _register_note(env)
    r = env.client.post(
        "/api/items",
        headers=hdr(env.write),
        json={"type": "note", "payload": {"nope": 1}},
    )
    assert r.status_code == 422


def test_submit_unknown_type_is_404(env):
    r = env.client.post(
        "/api/items", headers=hdr(env.write), json={"type": "ghost", "payload": {}}
    )
    assert r.status_code == 404


def test_get_submit_via_query_params(env):
    _register_note(env)
    r = env.client.get(
        "/api/submit",
        headers=hdr(env.write),
        params={"type": "note", "payload": json.dumps({"text": "from-get"})},
    )
    assert r.status_code == 201, r.text
    # and it shows up in the queue
    items = env.client.get("/api/items", headers=hdr(env.read)).json()
    assert any(i["payload"] == {"text": "from-get"} for i in items)


def test_get_submit_bad_json_is_400(env):
    _register_note(env)
    r = env.client.get(
        "/api/submit", headers=hdr(env.write), params={"type": "note", "payload": "{not json"}
    )
    assert r.status_code == 400


def test_poll_unread_then_ack_excludes(env):
    _register_note(env)
    env.client.post(
        "/api/items", headers=hdr(env.write), json={"type": "note", "payload": {"text": "a"}}
    )
    env.client.post(
        "/api/items", headers=hdr(env.write), json={"type": "note", "payload": {"text": "b"}}
    )
    items = env.client.get("/api/items", headers=hdr(env.read)).json()
    assert len(items) == 2
    ids = [items[0]["id"]]
    ack = env.client.post("/api/items/ack", headers=hdr(env.read), json={"ids": ids})
    assert ack.status_code == 200
    assert ack.json()["acked"] == 1
    remaining = env.client.get("/api/items", headers=hdr(env.read)).json()
    assert len(remaining) == 1


def test_poll_respects_type_and_limit(env):
    _register_note(env)
    for n in range(3):
        env.client.post(
            "/api/items", headers=hdr(env.write), json={"type": "note", "payload": {"text": str(n)}}
        )
    r = env.client.get("/api/items", headers=hdr(env.read), params={"limit": 2})
    assert len(r.json()) == 2
    r2 = env.client.get("/api/items", headers=hdr(env.read), params={"type": "note"})
    assert len(r2.json()) == 3
