"""Optional MaxMind GeoLite2 IP → (latitude, longitude) lookup.

Only loaded when ``GEOIP_DB_PATH`` is set. Failures during DB open or
individual lookups are non-fatal: callers receive ``None`` and the
exporter keeps publishing every other metric.
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

LatLon = tuple[float, float]


class GeoIPLookup:
    """Resolve IPs to ``(lat, lon)`` using a MaxMind GeoLite2-City database."""

    def __init__(self, db_path: str):
        try:
            import maxminddb  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without optional dep
            raise RuntimeError(
                "maxminddb is required for GeoIP lookups; "
                "install it or unset GEOIP_DB_PATH"
            ) from exc

        self._reader = maxminddb.open_database(db_path)
        log.info("Loaded GeoIP database from %s", db_path)

    def lookup(self, ip: str) -> Optional[LatLon]:
        """Return ``(lat, lon)`` rounded to 4 decimals, or ``None``."""
        if not ip:
            return None
        try:
            record = self._reader.get(ip)
        except (ValueError, KeyError):
            return None
        if not record:
            return None
        loc = record.get("location") or {}
        lat = loc.get("latitude")
        lon = loc.get("longitude")
        if lat is None or lon is None:
            return None
        return (round(float(lat), 4), round(float(lon), 4))

    def close(self) -> None:
        try:
            self._reader.close()
        except Exception:  # pragma: no cover
            pass
