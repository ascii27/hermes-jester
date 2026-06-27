"""Self-describing manifest so hermes can discover what's available and how to
consume it: every type's purpose, content shape, and concrete fetch URLs.
"""

from __future__ import annotations

from .examples import example_payload


def build_manifest(types: list[dict], base_url: str) -> dict:
    base = base_url.rstrip("/")
    return {
        "service": "hermes-jester",
        "base_url": base,
        "polling": {
            "description": (
                "Poll for new (unread) items across all types, process them, then "
                "ack their ids so they are not returned again. Use `since` (an "
                "ISO-8601 timestamp) to additionally window by time."
            ),
            "feed": f"GET {base}/api/items?unread=true&limit=50",
            "feed_since": f"GET {base}/api/items?unread=true&since=<iso8601>",
            "ack": f'POST {base}/api/items/ack  body: {{"ids": ["<id>", ...]}}',
            "mark_unread": f'PATCH {base}/api/item/<type>/<id>  body: {{"read": false}}',
            "auth": "Authorization: Bearer <read-scoped API key>",
        },
        "types": [_describe_type(t, base) for t in types],
    }


def _describe_type(t: dict, base: str) -> dict:
    name = t["name"]
    return {
        "name": name,
        "description": t.get("description", ""),
        "content_schema": t["schema"],
        "example_content": example_payload(t["schema"]),
        "fetch": {
            "unread": f"GET {base}/api/item/{name}?unread=true",
            "all": f"GET {base}/api/item/{name}?unread=false",
            "single_item": f"GET {base}/api/item/{name}/{{id}}",
        },
    }
