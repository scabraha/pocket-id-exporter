"""Runtime configuration for the exporter."""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


@dataclass(frozen=True)
class Config:
    """Exporter configuration, normally loaded from environment variables."""

    pocket_id_url: str
    api_key: str
    exporter_port: int = 9100
    poll_interval: int = 60
    request_timeout: int = 30
    log_level: str = "INFO"
    page_size: int = 100
    audit_window_hours: int = 24

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        """Build a Config from environment variables.

        Pass ``env`` to override ``os.environ`` (useful for tests).
        """
        env = env if env is not None else os.environ

        url = env.get("POCKET_ID_URL")
        if not url:
            raise ConfigError("POCKET_ID_URL is required")

        api_key = env.get("POCKET_ID_API_KEY")
        if not api_key:
            raise ConfigError("POCKET_ID_API_KEY is required")

        return cls(
            pocket_id_url=url.rstrip("/"),
            api_key=api_key,
            exporter_port=_int(env, "EXPORTER_PORT", 9100),
            poll_interval=_int(env, "POLL_INTERVAL", 60),
            request_timeout=_int(env, "REQUEST_TIMEOUT", 30),
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
            page_size=_int(env, "PAGE_SIZE", 100),
            audit_window_hours=_int(env, "AUDIT_WINDOW_HOURS", 24),
        )


def _int(env: dict[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
