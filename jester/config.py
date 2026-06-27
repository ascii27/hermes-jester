"""Environment-driven configuration.

Settings are read from environment variables once and exposed via `get_settings()`.
Tests construct `Settings` directly with overrides instead of touching the env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _split_emails(raw: str) -> list[str]:
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


@dataclass
class Settings:
    # Path to the SQLite database file. Default lives under ./data so it can sit
    # on the exe.dev persistent disk in production.
    db_path: str = "data/jester.db"

    # Signs the UI session cookie. MUST be overridden in production.
    secret_key: str = "dev-insecure-secret-change-me"

    # Google OAuth client credentials for the management UI.
    google_client_id: str = ""
    google_client_secret: str = ""

    # Public base URL of the service, used to build the OAuth redirect URI.
    base_url: str = "http://localhost:8000"

    # Google accounts permitted to use the management UI.
    allowed_emails: list[str] = field(
        default_factory=lambda: ["michael.roy.galloway@gmail.com"]
    )

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.base_url.rstrip('/')}/auth/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("JESTER_DB_PATH", "data/jester.db"),
        secret_key=os.environ.get("JESTER_SECRET_KEY", "dev-insecure-secret-change-me"),
        google_client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        base_url=os.environ.get("JESTER_BASE_URL", "http://localhost:8000"),
        allowed_emails=_split_emails(
            os.environ.get("JESTER_ALLOWED_EMAILS", "michael.roy.galloway@gmail.com")
        ),
    )
