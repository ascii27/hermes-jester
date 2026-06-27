import itertools

import pytest

from jester import items_repo, types_repo
from jester.errors import NotFoundError, PayloadInvalidError

NOTE_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


@pytest.fixture
def note_type(conn):
    types_repo.register_type(conn, "note", "A note", NOTE_SCHEMA)
    types_repo.register_type(conn, "link", "A link", {"type": "object"})
    return conn


@pytest.fixture
def fixed_clock(monkeypatch):
    """Make clock.now() return strictly increasing, predictable timestamps."""
    counter = itertools.count(1)
    stamps = []

    def fake_now():
        ts = f"2026-06-27T00:00:{next(counter):02d}.000000Z"
        stamps.append(ts)
        return ts

    monkeypatch.setattr("jester.clock.now", fake_now)
    return stamps


def test_submit_stores_item(note_type):
    item = items_repo.submit(
        note_type, "note", {"text": "hello"}, metadata={"src": "cli"}, source="key-a"
    )
    assert item["id"]
    assert item["type"] == "note"
    assert item["payload"] == {"text": "hello"}
    assert item["metadata"] == {"src": "cli"}
    assert item["source"] == "key-a"
    assert item["read_at"] is None

    fetched = items_repo.get_item(note_type, item["id"])
    assert fetched["payload"] == {"text": "hello"}


def test_submit_unknown_type_raises(note_type):
    with pytest.raises(NotFoundError):
        items_repo.submit(note_type, "ghost", {"text": "x"})


def test_submit_invalid_payload_raises(note_type):
    with pytest.raises(PayloadInvalidError):
        items_repo.submit(note_type, "note", {"wrong": "field"})


def test_query_returns_unread_by_default(note_type):
    a = items_repo.submit(note_type, "note", {"text": "a"})
    b = items_repo.submit(note_type, "note", {"text": "b"})
    items_repo.ack(note_type, [a["id"]])
    unread = items_repo.query_items(note_type)
    assert [i["id"] for i in unread] == [b["id"]]


def test_query_all_when_unread_false(note_type):
    a = items_repo.submit(note_type, "note", {"text": "a"})
    items_repo.ack(note_type, [a["id"]])
    items_repo.submit(note_type, "note", {"text": "b"})
    assert len(items_repo.query_items(note_type, unread=False)) == 2


def test_query_filters_by_type(note_type):
    items_repo.submit(note_type, "note", {"text": "a"})
    items_repo.submit(note_type, "link", {"url": "x"})
    notes = items_repo.query_items(note_type, type="note")
    assert all(i["type"] == "note" for i in notes)
    assert len(notes) == 1


def test_query_orders_ascending_and_respects_limit(note_type, fixed_clock):
    ids = [items_repo.submit(note_type, "note", {"text": str(n)})["id"] for n in range(5)]
    page = items_repo.query_items(note_type, limit=3)
    assert [i["id"] for i in page] == ids[:3]


def test_query_since_excludes_older(note_type, fixed_clock):
    items_repo.submit(note_type, "note", {"text": "old"})
    cutoff = fixed_clock[-1]
    newer = items_repo.submit(note_type, "note", {"text": "new"})
    result = items_repo.query_items(note_type, since=cutoff)
    assert [i["id"] for i in result] == [newer["id"]]


def test_ack_marks_read_and_returns_count(note_type):
    a = items_repo.submit(note_type, "note", {"text": "a"})
    b = items_repo.submit(note_type, "note", {"text": "b"})
    acked = items_repo.ack(note_type, [a["id"], b["id"]])
    assert acked == 2
    # Acking again is a no-op (already read)
    assert items_repo.ack(note_type, [a["id"]]) == 0
    assert items_repo.get_item(note_type, a["id"])["read_at"] is not None


def test_mark_unread_resets_read_at(note_type):
    a = items_repo.submit(note_type, "note", {"text": "a"})
    items_repo.ack(note_type, [a["id"]])
    items_repo.mark_unread(note_type, [a["id"]])
    assert items_repo.get_item(note_type, a["id"])["read_at"] is None


def test_delete_item(note_type):
    a = items_repo.submit(note_type, "note", {"text": "a"})
    assert items_repo.delete_item(note_type, a["id"]) is True
    assert items_repo.get_item(note_type, a["id"]) is None
    assert items_repo.delete_item(note_type, a["id"]) is False


def test_counts(note_type):
    a = items_repo.submit(note_type, "note", {"text": "a"})
    items_repo.submit(note_type, "note", {"text": "b"})
    items_repo.ack(note_type, [a["id"]])
    counts = items_repo.counts(note_type)
    assert counts == {"total": 2, "unread": 1}
