from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from jester import auth_ui, db, types_repo
from jester.app import create_app
from jester.auth_ui import require_user
from jester.config import Settings

NOTE_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}}


@pytest.fixture
def settings(tmp_path):
    db_file = str(tmp_path / "jester.db")
    c = db.connect(db_file)
    db.init_db(c)
    types_repo.register_type(c, "note", "A note", NOTE_SCHEMA)
    from jester import items_repo

    items_repo.submit(c, "note", {"text": "hi"}, source="seed")
    c.close()
    return Settings(db_path=db_file, allowed_emails=["allowed@example.com"])


@pytest.fixture
def app(settings):
    return create_app(settings)


# --- allowlist logic ---

def test_resolve_login_allows_listed_email(settings):
    user = auth_ui.resolve_login("allowed@example.com", settings)
    assert user["email"] == "allowed@example.com"


def test_resolve_login_rejects_unlisted_email(settings):
    assert auth_ui.resolve_login("intruder@example.com", settings) is None


def test_resolve_login_is_case_insensitive(settings):
    assert auth_ui.resolve_login("Allowed@Example.com", settings) is not None


# --- auth gate ---

def test_unauthenticated_ui_redirects_to_landing(app):
    client = TestClient(app, follow_redirects=False)
    r = client.get("/")
    assert r.status_code in (302, 303, 307)
    # unauthenticated users land on the public landing page, not straight at Google
    assert r.headers["location"] == "/login"


def test_landing_page_renders_with_signin(app):
    client = TestClient(app)
    r = client.get("/login")
    # the landing page renders without auth and offers Google sign-in
    assert r.status_code == 200
    assert "Google" in r.text
    assert "/auth/login" in r.text


# --- authenticated pages (require_user overridden) ---

@pytest.fixture
def auth_client(app):
    app.dependency_overrides[require_user] = lambda: {"email": "allowed@example.com"}
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_dashboard_shows_counts(auth_client):
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "note" in r.text  # types listed or counted


def test_items_page_lists_seeded_item(auth_client):
    r = auth_client.get("/ui/items")
    assert r.status_code == 200
    assert "note" in r.text


def test_types_page_renders(auth_client):
    r = auth_client.get("/ui/types")
    assert r.status_code == 200
    assert "note" in r.text


def test_keys_page_renders(auth_client):
    r = auth_client.get("/ui/keys")
    assert r.status_code == 200
