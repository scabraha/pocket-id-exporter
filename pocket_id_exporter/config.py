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
    log_format: str = "text"
    page_size: int = 100
    audit_window_hours: int = 24
    geoip_db_path: str = ""
    track_user_logins: bool = True

    def sanitized(self) -> dict:
        """Return the config as a dict with secrets redacted, for logging."""
        from dataclasses import asdict
        data = asdict(self)
        if data.get("api_key"):
            data["api_key"] = "***"
        return data

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

        log_format = env.get("LOG_FORMAT", "text").lower()
        if log_format not in ("text", "json"):
            raise ConfigError(f"LOG_FORMAT must be 'text' or 'json', got {log_format!r}")

        return cls(
            pocket_id_url=url.rstrip("/"),
            api_key=api_key,
            exporter_port=_int(env, "EXPORTER_PORT", 9100),
            poll_interval=_int(env, "POLL_INTERVAL", 60),
            request_timeout=_int(env, "REQUEST_TIMEOUT", 30),
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
            log_format=log_format,
            page_size=_int(env, "PAGE_SIZE", 100),
            audit_window_hours=_int(env, "AUDIT_WINDOW_HOURS", 24),
            geoip_db_path=env.get("GEOIP_DB_PATH", ""),
            track_user_logins=_bool(env, "TRACK_USER_LOGINS", True),
        )


def _int(env: dict[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _bool(env: dict[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{key} must be a boolean, got {raw!r}")

