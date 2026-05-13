"""Polling loop that drives metric updates."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections import Counter as CounterDict
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from .audit import AuditEntry
from .client import PocketIDClient
from .config import Config
from .geoip import GeoIPLookup
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
        geoip: GeoIPLookup | None = None,
        clock=None,
    ):
        self._client = client
        self._metrics = metrics
        self._config = config
        self._geoip = geoip
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_seen_ts: str = ""
        self._known_user_countries: dict[str, set[str]] = defaultdict(set)

    # -- public API -----------------------------------------------------

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

    # -- inventory ------------------------------------------------------

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

    # -- audit log ------------------------------------------------------

    def _poll_audit_data(self) -> None:
        """Fetch recent audit logs once and update all derived metrics."""
        window_cutoff_iso = (
            self._clock() - timedelta(hours=self._config.audit_window_hours)
        ).isoformat()

        if not self._last_seen_ts:
            self._last_seen_ts = window_cutoff_iso

        fetch_cutoff = min(self._last_seen_ts, window_cutoff_iso)
        raw_entries = self._client.fetch_audit_logs_since(fetch_cutoff)
        entries = [AuditEntry.from_api(e) for e in raw_entries]

        new_entries = [e for e in entries if e.created_at > self._last_seen_ts]
        window_entries = [e for e in entries if e.created_at > window_cutoff_iso]

        self._handle_new_entries(new_entries)
        self._update_window_metrics(window_entries)

    def _handle_new_entries(self, entries: list[AuditEntry]) -> None:
        """Update cumulative counters from events newer than the last poll."""
        if not entries:
            return

        latest_ts = self._last_seen_ts
        for entry in entries:
            self._metrics.audit_events.labels(
                event=entry.event, client_name=entry.client_name
            ).inc()

            if self._config.track_user_logins and entry.is_login and entry.username:
                self._track_user_login(entry)

            if entry.created_at > latest_ts:
                latest_ts = entry.created_at

        self._last_seen_ts = latest_ts
        log.info("Processed %d new audit events", len(entries))

    def _track_user_login(self, entry: AuditEntry) -> None:
        self._metrics.user_logins.labels(
            username=entry.username, country=entry.country
        ).inc()

        seen = self._known_user_countries[entry.username]
        if entry.country not in seen:
            seen.add(entry.country)
            self._metrics.user_new_country_logins.labels(
                username=entry.username, country=entry.country
            ).inc()

    def _update_window_metrics(self, entries: Iterable[AuditEntry]) -> None:
        """Recompute gauges that describe the recent window."""
        events_by_geo: CounterDict = CounterDict()
        events_by_location: CounterDict = CounterDict({"internal": 0, "external": 0})
        events_by_coords: CounterDict = CounterDict()

        for entry in entries:
            events_by_geo[(entry.event, entry.country, entry.city)] += 1
            events_by_location[classify_ip(entry.ip)] += 1
            coords = self._lookup_coords(entry.ip)
            if coords is not None:
                events_by_coords[(entry.country, entry.city, coords)] += 1

        self._set_gauge(
            self._metrics.recent_events,
            {("event", "country", "city"): events_by_geo},
        )
        self._set_gauge(
            self._metrics.events_by_location,
            {("location",): events_by_location},
        )
        if self._geoip is not None:
            geo_with_str_coords = {
                (country, city, f"{lat:.4f}", f"{lon:.4f}"): count
                for (country, city, (lat, lon)), count in events_by_coords.items()
            }
            self._set_gauge(
                self._metrics.event_geolocation,
                {("country", "city", "latitude", "longitude"): geo_with_str_coords},
            )

    def _lookup_coords(self, ip: str) -> Optional[tuple[float, float]]:
        if self._geoip is None:
            return None
        return self._geoip.lookup(ip)

    @staticmethod
    def _set_gauge(gauge, label_data: dict) -> None:
        """Replace a gauge's labelled values with a fresh set of samples."""
        gauge.clear()
        for label_names, counts in label_data.items():
            for labels, value in counts.items():
                if not isinstance(labels, tuple):
                    labels = (labels,)
                kwargs = dict(zip(label_names, labels))
                gauge.labels(**kwargs).set(value)
