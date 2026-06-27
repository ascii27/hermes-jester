import pytest

from jester import types_repo
from jester.errors import ConflictError, NotFoundError, SchemaInvalidError

NOTE_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


def test_register_and_get_type(conn):
    created = types_repo.register_type(conn, "note", "A note", NOTE_SCHEMA)
    assert created["name"] == "note"
    assert created["description"] == "A note"
    assert created["schema"] == NOTE_SCHEMA
    assert created["created_at"]

    fetched = types_repo.get_type(conn, "note")
    assert fetched["name"] == "note"
    assert fetched["schema"] == NOTE_SCHEMA


def test_get_missing_type_returns_none(conn):
    assert types_repo.get_type(conn, "nope") is None


def test_register_duplicate_type_conflicts(conn):
    types_repo.register_type(conn, "note", "A note", NOTE_SCHEMA)
    with pytest.raises(ConflictError):
        types_repo.register_type(conn, "note", "Dup", NOTE_SCHEMA)


def test_register_invalid_schema_rejected(conn):
    # "type": 123 is not a valid JSON Schema keyword value
    with pytest.raises(SchemaInvalidError):
        types_repo.register_type(conn, "bad", "", {"type": 123})


def test_list_types(conn):
    types_repo.register_type(conn, "note", "", NOTE_SCHEMA)
    types_repo.register_type(conn, "link", "", NOTE_SCHEMA)
    names = sorted(t["name"] for t in types_repo.list_types(conn))
    assert names == ["link", "note"]


def test_update_type(conn):
    types_repo.register_type(conn, "note", "old", NOTE_SCHEMA)
    new_schema = {"type": "object", "properties": {"body": {"type": "string"}}}
    updated = types_repo.update_type(conn, "note", description="new", schema=new_schema)
    assert updated["description"] == "new"
    assert updated["schema"] == new_schema
    assert types_repo.get_type(conn, "note")["schema"] == new_schema


def test_update_missing_type_raises(conn):
    with pytest.raises(NotFoundError):
        types_repo.update_type(conn, "ghost", description="x")


def test_update_invalid_schema_rejected(conn):
    types_repo.register_type(conn, "note", "", NOTE_SCHEMA)
    with pytest.raises(SchemaInvalidError):
        types_repo.update_type(conn, "note", schema={"type": 123})
