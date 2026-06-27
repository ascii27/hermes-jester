"""Generate a sample payload from a type's JSON Schema, for UI usage examples."""

from __future__ import annotations

from typing import Any


def example_payload(schema: dict) -> Any:
    """Build a representative example value for `schema`. Best-effort: covers the
    common JSON Schema shapes (object/array/string/number/boolean/enum)."""
    if not isinstance(schema, dict):
        return None

    if "example" in schema:
        return schema["example"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

    t = schema.get("type")
    if isinstance(t, list):
        t = t[0] if t else None

    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        required = schema.get("required")
        out = {}
        for key, sub in props.items():
            # include required fields; if none are marked required, include all
            if required is None or key in required:
                out[key] = example_payload(sub)
        return out
    if t == "array":
        item_schema = schema.get("items")
        return [example_payload(item_schema)] if item_schema else []
    if t == "string":
        return schema.get("format", "string")
    if t in ("integer", "number"):
        return 0
    if t == "boolean":
        return True
    return None
