"""Bearer API-key authentication and scope enforcement for /api routes."""

from __future__ import annotations

import sqlite3

from fastapi import Depends, Header, HTTPException

from . import keys_repo
from .deps import get_conn


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def require_scope(needed: str):
    """Build a dependency that requires an active key whose scope satisfies `needed`."""

    def dependency(
        authorization: str | None = Header(default=None),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict:
        token = _extract_bearer(authorization)
        key = keys_repo.authenticate(conn, token) if token else None
        if key is None:
            raise HTTPException(status_code=401, detail="invalid or missing API key")
        if not keys_repo.scope_allows(key["scope"], needed):
            raise HTTPException(
                status_code=403,
                detail=f"this key has scope '{key['scope']}', '{needed}' required",
            )
        return key

    return dependency
