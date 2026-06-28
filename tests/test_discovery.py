from jester.discovery import build_manifest

TYPES = [
    {
        "name": "message",
        "description": "A command/message for hermes",
        "schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "created_at": "t",
        "updated_at": "t",
    }
]


def test_manifest_top_level():
    m = build_manifest(TYPES, "https://lectern-queenside.exe.xyz/")
    assert m["service"] == "hermes-jester"
    # trailing slash on base_url is normalized
    assert m["base_url"] == "https://lectern-queenside.exe.xyz"
    assert "polling" in m and "types" in m


def test_polling_section_describes_feed_and_ack():
    m = build_manifest(TYPES, "https://x")
    p = m["polling"]
    assert "/api/items" in p["feed"]
    assert "/api/items/ack" in p["ack"]


def test_type_entry_has_purpose_content_and_fetch():
    m = build_manifest(TYPES, "https://x")
    t = m["types"][0]
    assert t["name"] == "message"
    assert t["description"] == "A command/message for hermes"          # what it's for
    assert t["content_schema"]["properties"]["text"]["type"] == "string"  # what the content is
    assert t["example_content"] == {"text": "string"}                  # concrete example
    # how to fetch it: concrete, absolute URLs
    assert t["fetch"]["unread"] == "GET https://x/api/item/message?unread=true"
    assert "https://x/api/item/message/{id}" in t["fetch"]["single_item"]


def test_empty_types():
    m = build_manifest([], "https://x")
    assert m["types"] == []
