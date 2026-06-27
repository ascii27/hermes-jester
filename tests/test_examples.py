from jester.examples import example_payload


def test_object_with_required_fields():
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}, "n": {"type": "integer"}},
        "required": ["text"],
    }
    # required field present with a typed placeholder
    ex = example_payload(schema)
    assert ex["text"] == "string"


def test_uses_explicit_example_when_present():
    schema = {"type": "object", "properties": {"url": {"type": "string", "example": "https://x"}}}
    assert example_payload(schema)["url"] == "https://x"


def test_enum_picks_first():
    schema = {"type": "object", "properties": {"level": {"enum": ["low", "high"]}}}
    assert example_payload(schema)["level"] == "low"


def test_nested_and_array():
    schema = {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "items": {"type": "string"}},
            "meta": {"type": "object", "properties": {"k": {"type": "boolean"}}},
        },
    }
    ex = example_payload(schema)
    assert ex["tags"] == ["string"]
    assert ex["meta"] == {"k": True}


def test_non_object_schema():
    assert example_payload({"type": "string"}) == "string"
