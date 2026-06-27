"""Shared FastAPI dependencies."""

from __future__ import annotations

import sqlite3
from typing import Iterator

from fastapi import Request

from . import db
from .config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection for the duration of the request."""
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()
