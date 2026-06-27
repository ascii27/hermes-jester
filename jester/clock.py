"""Single source of truth for timestamps.

All timestamps in hermes-jester are UTC, formatted as ISO 8601 strings with a
trailing 'Z'. Stored as TEXT in SQLite, they sort lexically in chronological
order, which is what the `created_at` ordering and `since` filters rely on.
"""

from datetime import datetime, timezone


def now() -> str:
    """Return the current time as an ISO 8601 UTC string, e.g. 2026-06-27T18:30:00.123456Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
