"""Parsed audit-log entry.

Wraps Pocket-ID's audit log API payload so the rest of the codebase can
work with attribute access instead of nested ``dict.get`` chains.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import LOGIN_EVENTS

UNKNOWN = "Unknown"


@dataclass(frozen=True)
class AuditEntry:
    """Normalised audit log entry."""

    created_at: str
    event: str
    username: str
    country: str
    city: str
    ip: str
    client_name: str

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "AuditEntry":
        """Build an entry from the raw Pocket-ID API payload.

        Missing or null fields are coerced to empty strings (or
        ``"Unknown"`` for country/city) so consumers don't need to
        duplicate the same defensive logic everywhere.
        """
        data = raw.get("data") or {}
        return cls(
            created_at=raw.get("createdAt") or "",
            event=raw.get("event") or "UNKNOWN",
            username=raw.get("username") or "",
            country=raw.get("country") or UNKNOWN,
            city=raw.get("city") or UNKNOWN,
            ip=raw.get("ipAddress") or "",
            client_name=data.get("clientName", "") or "",
        )

    @property
    def is_login(self) -> bool:
        """True if this event represents a user login."""
        return self.event in LOGIN_EVENTS
