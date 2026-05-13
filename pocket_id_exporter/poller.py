"""Polling loop that drives metric updates."""

from __future__ import annotations

import logging
import threading
from collections import Counter as CounterDict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .client import PocketIDClient
from .config import Config
from .metrics import Metrics, classify_ip

log = logging.getLogger(__name__)


class Poller:
    """Periodically polls Pocket-ID and updates Prometheus metrics."""

    def __init__(
        self,
        client: PocketIDClient,
        metrics: Metrics,
        config: Config,
        *,
        clock=None,
    ):
        self._client = client
        self._metrics = metrics
        self._config = config
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_seen_ts: str = ""

    def poll_once(self) -> None:
        """Run a single poll cycle, updating all metrics."""
        try:
            self._poll_version()
            self._poll_counts()
            self._poll_audit_data()
            self._metrics.up.set(1)
        except Exception:
            log.exception("Poll failed")
            self._metrics.up.set(0)

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        """Poll in a loop until ``stop_event`` is set."""
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            self.poll_once()
            stop_event.wait(self._config.poll_interval)

    def _poll_version(self) -> None:
        self._metrics.version_info.info({"version": self._client.version()})

    def _poll_counts(self) -> None:
        self._metrics.users_total.set(self._client.total_items("/api/users"))
        self._metrics.oidc_clients_total.set(
            self._client.total_items("/api/oidc/clients")
        )
        self._metrics.user_groups_total.set(
            self._client.total_items("/api/user-groups")
        )

    def _poll_audit_data(self) -> None:
        """Fetch recent audit logs once, then update both delta and window metrics."""
        window_cutoff = self._clock() - timedelta(
            hours=self._config.audit_window_hours
        )
        window_cutoff_iso = window_cutoff.isoformat()

        if not self._last_seen_ts:
            self._last_seen_ts = window_cutoff_iso

        # Fetch only as far back as the older of the two cutoffs (window or last-seen).
        fetch_cutoff = min(self._last_seen_ts, window_cutoff_iso)
        entries = self._client.fetch_audit_logs_since(fetch_cutoff)

        self._update_event_counters(entries)
        self._update_geo_gauges(e for e in entries if e.get("createdAt", "") > window_cutoff_iso)

    def _update_event_counters(self, entries: list[dict]) -> None:
        new_events = [e for e in entries if e.get("createdAt", "") > self._last_seen_ts]
        if not new_events:
            return

        latest_ts = self._last_seen_ts
        for entry in new_events:
            event = entry.get("event", "UNKNOWN")
            data = entry.get("data") or {}
            client_name = data.get("clientName", "")
            self._metrics.audit_events.labels(
                event=event, client_name=client_name
            ).inc()
            ts = entry.get("createdAt", "")
            if ts > latest_ts:
                latest_ts = ts

        self._last_seen_ts = latest_ts
        log.info("Processed %d new audit events", len(new_events))

    def _update_geo_gauges(self, entries: Iterable[dict]) -> None:
        country_counts: CounterDict[str] = CounterDict()
        location_counts: CounterDict[str] = CounterDict({"internal": 0, "external": 0})

        for entry in entries:
            country_counts[entry.get("country") or "Unknown"] += 1
            location_counts[classify_ip(entry.get("ipAddress", ""))] += 1

        self._metrics.events_by_country.clear()
        for country, count in country_counts.items():
            self._metrics.events_by_country.labels(country=country).set(count)

        self._metrics.events_by_location.clear()
        for location, count in location_counts.items():
            self._metrics.events_by_location.labels(location=location).set(count)
