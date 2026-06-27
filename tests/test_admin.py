import json

from jester import admin, keys_repo, types_repo


def test_create_key_cmd_returns_token(conn):
    out = admin.create_key_cmd(conn, "hermes", "read")
    assert "jstr_" in out
    # the key is persisted and the printed token authenticates
    token = next(line.split()[-1] for line in out.splitlines() if "jstr_" in line)
    assert keys_repo.authenticate(conn, token)["name"] == "hermes"


def test_list_keys_cmd(conn):
    keys_repo.create_key(conn, "a", "read")
    out = admin.list_keys_cmd(conn)
    assert "a" in out
    assert "read" in out


def test_revoke_key_cmd(conn):
    record, token = keys_repo.create_key(conn, "a", "read")
    admin.revoke_key_cmd(conn, record["id"])
    assert keys_repo.authenticate(conn, token) is None


def test_register_type_cmd(conn, tmp_path):
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    schema_file = tmp_path / "s.json"
    schema_file.write_text(json.dumps(schema))
    admin.register_type_cmd(conn, "note", "A note", str(schema_file))
    assert types_repo.get_type(conn, "note")["schema"] == schema
