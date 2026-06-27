import pytest

from jester import keys_repo
from jester.errors import NotFoundError


def test_create_key_returns_plaintext_once(conn):
    record, token = keys_repo.create_key(conn, "hermes", "read")
    assert record["name"] == "hermes"
    assert record["scope"] == "read"
    assert record["revoked_at"] is None
    assert token.startswith("jstr_")
    # The plaintext is not stored anywhere retrievable
    assert "token" not in record
    assert keys_repo.get_key(conn, record["id"])["token_hash"] != token


def test_create_key_rejects_bad_scope(conn):
    with pytest.raises(ValueError):
        keys_repo.create_key(conn, "x", "superuser")


def test_authenticate_resolves_active_key(conn):
    record, token = keys_repo.create_key(conn, "sender", "write")
    resolved = keys_repo.authenticate(conn, token)
    assert resolved["id"] == record["id"]
    assert resolved["scope"] == "write"


def test_authenticate_unknown_token_returns_none(conn):
    assert keys_repo.authenticate(conn, "jstr_nope") is None


def test_authenticate_revoked_key_returns_none(conn):
    record, token = keys_repo.create_key(conn, "sender", "write")
    keys_repo.revoke_key(conn, record["id"])
    assert keys_repo.authenticate(conn, token) is None


def test_revoke_missing_key_raises(conn):
    with pytest.raises(NotFoundError):
        keys_repo.revoke_key(conn, "ghost")


def test_list_keys(conn):
    keys_repo.create_key(conn, "a", "read")
    keys_repo.create_key(conn, "b", "write")
    names = sorted(k["name"] for k in keys_repo.list_keys(conn))
    assert names == ["a", "b"]
    # token_hash is internal but listing should not leak plaintext
    assert all("token" not in k for k in keys_repo.list_keys(conn))


def test_scope_allows_hierarchy():
    assert keys_repo.scope_allows("admin", "write")
    assert keys_repo.scope_allows("admin", "read")
    assert keys_repo.scope_allows("write", "write")
    assert not keys_repo.scope_allows("write", "read")
    assert not keys_repo.scope_allows("read", "write")
