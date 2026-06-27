"""Command-line admin tool: bootstrap the database, mint keys, register types.

Used before the UI is reachable, e.g. to create the first admin key and hermes's
read key. Run as `jester-admin <command>` or `python -m jester.admin <command>`.
"""

from __future__ import annotations

import argparse
import json
import sqlite3

from . import db, keys_repo, types_repo
from .config import get_settings


def init_db_cmd(conn: sqlite3.Connection) -> str:
    db.init_db(conn)
    return "database initialized"


def create_key_cmd(conn: sqlite3.Connection, name: str, scope: str) -> str:
    record, token = keys_repo.create_key(conn, name, scope)
    return (
        f"created key id={record['id']} name={record['name']} scope={record['scope']}\n"
        f"token (shown once, store it now): {token}"
    )


def list_keys_cmd(conn: sqlite3.Connection) -> str:
    keys = keys_repo.list_keys(conn)
    if not keys:
        return "(no keys)"
    lines = []
    for k in keys:
        state = f"revoked {k['revoked_at']}" if k["revoked_at"] else "active"
        lines.append(f"{k['id']}  {k['scope']:<6}  {k['name']:<20}  {state}")
    return "\n".join(lines)


def revoke_key_cmd(conn: sqlite3.Connection, key_id: str) -> str:
    keys_repo.revoke_key(conn, key_id)
    return f"revoked key {key_id}"


def register_type_cmd(
    conn: sqlite3.Connection, name: str, description: str, schema_file: str
) -> str:
    with open(schema_file) as f:
        schema = json.load(f)
    types_repo.register_type(conn, name, description, schema)
    return f"registered type {name!r}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jester-admin")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create tables and indexes")

    p_create = sub.add_parser("create-key", help="mint a new API key")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--scope", required=True, choices=keys_repo.VALID_SCOPES)

    sub.add_parser("list-keys", help="list API keys")

    p_revoke = sub.add_parser("revoke-key", help="revoke an API key")
    p_revoke.add_argument("key_id")

    p_type = sub.add_parser("register-type", help="register a data type from a schema file")
    p_type.add_argument("--name", required=True)
    p_type.add_argument("--description", default="")
    p_type.add_argument("--schema-file", required=True)

    args = parser.parse_args(argv)
    conn = db.connect(get_settings().db_path)
    db.init_db(conn)
    try:
        if args.command == "init-db":
            print(init_db_cmd(conn))
        elif args.command == "create-key":
            print(create_key_cmd(conn, args.name, args.scope))
        elif args.command == "list-keys":
            print(list_keys_cmd(conn))
        elif args.command == "revoke-key":
            print(revoke_key_cmd(conn, args.key_id))
        elif args.command == "register-type":
            print(register_type_cmd(conn, args.name, args.description, args.schema_file))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
