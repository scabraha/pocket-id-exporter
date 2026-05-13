"""Pocket-ID Prometheus Exporter

Polls the Pocket-ID admin API for audit logs, user counts, and OIDC client
info, then exposes the data as Prometheus metrics.

Required environment variables:
  POCKET_ID_URL      – Base URL of the Pocket-ID instance (e.g. http://pocket:1411)
  POCKET_ID_API_KEY  – Admin-scoped API key

Optional:
  EXPORTER_PORT      – Port to listen on (default 9100)
  POLL_INTERVAL      – Seconds between API polls (default 60)
"""

import os
import time
import logging
import threading
from datetime import datetime, timezone, timedelta

import requests
from prometheus_client import (
    Counter,
    Gauge,
    Info,
    start_http_server,
    REGISTRY,
)
from prometheus_client.registry import Collector

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("pocket-id-exporter")

POCKET_ID_URL = os.environ["POCKET_ID_URL"].rstrip("/")
API_KEY = os.environ["POCKET_ID_API_KEY"]
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
EXPORTER_PORT = int(os.getenv("EXPORTER_PORT", "9100"))

HEADERS = {"X-API-Key": API_KEY}
PAGE_SIZE = 100

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

# Counters – monotonically increasing, survive restarts via last-seen tracking
audit_events = Counter(
    "pocketid_audit_events_total",
    "Total audit log events observed",
    ["event", "client_name"],
)

# Gauges – snapshot values refreshed each poll
users_total = Gauge("pocketid_users_total", "Total registered users")
oidc_clients_total = Gauge("pocketid_oidc_clients_total", "Total OIDC clients")
user_groups_total = Gauge("pocketid_user_groups_total", "Total user groups")

events_by_country = Gauge(
    "pocketid_recent_events_by_country",
    "Audit events in the last 24 hours by country",
    ["country"],
)
events_by_location = Gauge(
    "pocketid_recent_events_by_location",
    "Audit events in the last 24 hours by network location",
    ["location"],
)

version_info = Info("pocketid_version", "Pocket-ID version information")

up_gauge = Gauge("pocketid_up", "Whether the exporter can reach Pocket-ID")

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def api_get(path, params=None):
    """GET from Pocket-ID API with automatic error handling."""
    url = f"{POCKET_ID_URL}{path}"
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_paginated_count(path):
    """Fetch only the first page with limit=1 to read totalItems."""
    data = api_get(path, {"pagination[page]": 1, "pagination[limit]": 1})
    return data.get("pagination", {}).get("totalItems", 0)


def fetch_all_audit_logs_since(since_iso):
    """Fetch all audit log entries created after since_iso (paginated)."""
    page = 1
    all_entries = []
    while True:
        params = {
            "pagination[page]": page,
            "pagination[limit]": PAGE_SIZE,
            "sort[column]": "createdAt",
            "sort[direction]": "asc",
        }
        data = api_get("/api/audit-logs/all", params)
        entries = data.get("data", [])
        pagination = data.get("pagination", {})

        for entry in entries:
            created = entry.get("createdAt", "")
            if created > since_iso:
                all_entries.append(entry)

        if page >= pagination.get("totalPages", 1):
            break
        page += 1

    return all_entries


# ---------------------------------------------------------------------------
# Polling logic
# ---------------------------------------------------------------------------


class PocketIDPoller:
    """Background thread that periodically polls the Pocket-ID API."""

    def __init__(self):
        self._last_seen_ts = ""
        self._lock = threading.Lock()

    def poll(self):
        try:
            self._poll_version()
            self._poll_counts()
            self._poll_audit_logs()
            self._poll_recent_geo()
            up_gauge.set(1)
        except Exception:
            log.exception("Poll failed")
            up_gauge.set(0)

    def _poll_version(self):
        data = api_get("/api/version/current")
        v = data if isinstance(data, str) else data.get("version", "unknown")
        version_info.info({"version": v})

    def _poll_counts(self):
        users_total.set(fetch_paginated_count("/api/users"))
        oidc_clients_total.set(fetch_paginated_count("/api/oidc/clients"))
        user_groups_total.set(fetch_paginated_count("/api/user-groups"))

    def _poll_audit_logs(self):
        """Fetch new audit events and increment counters."""
        if not self._last_seen_ts:
            # First run: seed from the last 24 hours
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            self._last_seen_ts = cutoff.isoformat()

        entries = fetch_all_audit_logs_since(self._last_seen_ts)
        if not entries:
            return

        latest_ts = self._last_seen_ts
        for entry in entries:
            event = entry.get("event", "UNKNOWN")
            client_name = (entry.get("data") or {}).get("clientName", "")
            audit_events.labels(event=event, client_name=client_name).inc()
            ts = entry.get("createdAt", "")
            if ts > latest_ts:
                latest_ts = ts

        with self._lock:
            self._last_seen_ts = latest_ts
        log.info("Processed %d new audit events", len(entries))

    def _poll_recent_geo(self):
        """Gauge of events in the last 24h broken down by country and location."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        cutoff_iso = cutoff.isoformat()

        entries = fetch_all_audit_logs_since(cutoff_iso)

        country_counts: dict[str, int] = {}
        location_counts: dict[str, int] = {"internal": 0, "external": 0}

        for entry in entries:
            country = entry.get("country") or "Unknown"
            country_counts[country] = country_counts.get(country, 0) + 1

            ip = entry.get("ipAddress", "")
            if ip.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                              "172.20.", "172.21.", "172.22.", "172.23.",
                              "172.24.", "172.25.", "172.26.", "172.27.",
                              "172.28.", "172.29.", "172.30.", "172.31.",
                              "192.168.", "127.")):
                location_counts["internal"] += 1
            else:
                location_counts["external"] += 1

        # Reset and set fresh values
        events_by_country._metrics.clear()
        for country, count in country_counts.items():
            events_by_country.labels(country=country).set(count)

        events_by_location._metrics.clear()
        for loc, count in location_counts.items():
            events_by_location.labels(location=loc).set(count)

    def run_forever(self):
        while True:
            self.poll()
            time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("Starting Pocket-ID exporter on :%d (poll every %ds)", EXPORTER_PORT, POLL_INTERVAL)
    log.info("Pocket-ID URL: %s", POCKET_ID_URL)

    start_http_server(EXPORTER_PORT)

    poller = PocketIDPoller()
    poller.run_forever()


if __name__ == "__main__":
    main()
