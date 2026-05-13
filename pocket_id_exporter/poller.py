"""Polling loop that drives metric updates."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from collections import Counter as CounterDict
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import requests

from .audit import AuditEntry
from .client import PocketIDClient
from .config import Config
from .geoip import GeoIPLookup
from .metrics import Metrics, classify_ip

log = logging.getLogger(__name__)


class _StepFailure(Exception):
    """Internal: marks which poll step raised, for error context."""

    def __init__(self, step: str, original: BaseException):
        super().__init__(step)
        self.step = step
        self.original = original


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
        self._has_succeeded_once = False
        self._consecutive_failures = 0

    # -- public API -----------------------------------------------------

    def poll_once(self) -> None:
        """Run a single poll cycle, updating all metrics."""
        started = time.monotonic()
        try:
            self._run_step("version", self._poll_version)
            self._run_step("counts", self._poll_counts)
            self._run_step("audit", self._poll_audit_data)
        except _StepFailure as fail:
            self._record_failure(fail, time.monotonic() - started)
            return
        self._record_success(time.monotonic() - started)

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        """Poll in a loop until ``stop_event`` is set."""
        stop_event = stop_event or threading.Event()
        log.info(
            "Poll loop starting (interval=%ds, audit_window=%dh)",
            self._config.poll_interval, self._config.audit_window_hours,
        )
        while not stop_event.is_set():
            self.poll_once()
            stop_event.wait(self._config.poll_interval)
        log.info("Poll loop stopped")

    # -- step orchestration --------------------------------------------

    @staticmethod
    def _run_step(name: str, fn) -> None:
        try:
            fn()
        except BaseException as exc:
            raise _StepFailure(name, exc) from exc

    def _record_success(self, duration_s: float) -> None:
        self._metrics.up.set(1)
        self._metrics.poll_duration.set(duration_s)
        self._metrics.last_successful_poll.set(time.time())

        if not self._has_succeeded_once:
            self._has_succeeded_once = True
            log.info(
                "First successful poll cycle in %.2fs; exporter is healthy",
                duration_s,
            )
        elif self._consecutive_failures > 0:
            log.info(
                "Recovered after %d consecutive failures (poll took %.2fs)",
                self._consecutive_failures, duration_s,
            )
        else:
            log.debug("Poll cycle completed in %.2fs", duration_s)
        self._consecutive_failures = 0

    def _record_failure(self, fail: _StepFailure, duration_s: float) -> None:
        self._metrics.up.set(0)
        self._metrics.poll_duration.set(duration_s)
        self._metrics.poll_failures.labels(step=fail.step).inc()
        self._consecutive_failures += 1

        exc = fail.original
        # HTTPError messages from PocketIDClient already include status + path
        # so they're useful as a single line; keep stack trace at DEBUG.
        if isinstance(exc, requests.HTTPError):
            log.error(
                "Poll step '%s' failed (consecutive_failures=%d): %s",
                fail.step, self._consecutive_failures, exc,
            )
            log.debug("HTTPError details", exc_info=(type(exc), exc, exc.__traceback__))
        else:
            log.error(
                "Poll step '%s' failed (consecutive_failures=%d)",
                fail.step, self._consecutive_failures,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    # -- inventory ------------------------------------------------------

    def _poll_version(self) -> None:
        version = self._client.version()
        self._metrics.version_info.info({"version": version})
        log.debug("Pocket-ID version=%s", version)

    def _poll_counts(self) -> None:
        users = self._client.total_items("/api/users")
        clients = self._client.total_items("/api/oidc/clients")
        groups = self._client.total_items("/api/user-groups")
        self._metrics.users_total.set(users)
        self._metrics.oidc_clients_total.set(clients)
        self._metrics.user_groups_total.set(groups)
        log.debug(
            "Inventory counts: users=%d oidc_clients=%d user_groups=%d",
            users, clients, groups,
        )

    # -- audit log ------------------------------------------------------

    def _poll_audit_data(self) -> None:
        """Fetch recent audit logs once and update all derived metrics."""
        window_cutoff_iso = (
            self._clock() - timedelta(hours=self._config.audit_window_hours)
        ).isoformat()

        if not self._last_seen_ts:
            self._last_seen_ts = window_cutoff_iso
            log.info("Seeding last_seen cursor from window start: %s", window_cutoff_iso)

        fetch_cutoff = min(self._last_seen_ts, window_cutoff_iso)
        raw_entries = self._client.fetch_audit_logs_since(fetch_cutoff)
        entries = [AuditEntry.from_api(e) for e in raw_entries]

        new_entries = [e for e in entries if e.created_at > self._last_seen_ts]
        window_entries = [e for e in entries if e.created_at > window_cutoff_iso]

        self._handle_new_entries(new_entries)
        self._update_window_metrics(window_entries)

        log.debug(
            "Audit poll: fetched=%d new=%d in_window=%d",
            len(entries), len(new_entries), len(window_entries),
        )

    def _handle_new_entries(self, entries: list[AuditEntry]) -> None:
        """Update cumulative counters from events newer than the last poll."""
        if not entries:
            return

        latest_ts = self._last_seen_ts
        login_count = 0
        new_country_count = 0
        for entry in entries:
            self._metrics.audit_events.labels(
                event=entry.event, client_name=entry.client_name
            ).inc()

            if self._config.track_user_logins and entry.is_login and entry.username:
                fired = self._track_user_login(entry)
                login_count += 1
                new_country_count += int(fired)

            if entry.created_at > latest_ts:
                latest_ts = entry.created_at

        self._last_seen_ts = latest_ts
        log.info(
            "Processed %d new audit events (logins=%d new_countries=%d)",
            len(entries), login_count, new_country_count,
        )

    def _track_user_login(self, entry: AuditEntry) -> bool:
        """Increment per-user counters; return True if this was a new country."""
        self._metrics.user_logins.labels(
            username=entry.username, country=entry.country
        ).inc()

        seen = self._known_user_countries[entry.username]
        if entry.country in seen:
            return False
        seen.add(entry.country)
        self._metrics.user_new_country_logins.labels(
            username=entry.username, country=entry.country
        ).inc()
        log.warning(
            "First-seen country for user: username=%s country=%s",
            entry.username, entry.country,
        )
        return True

    def _update_window_metrics(self, entries: Iterable[AuditEntry]) -> None:
        """Recompute gauges that describe the recent window."""
        events_by_geo: CounterDict = CounterDict()
        events_by_location: CounterDict = CounterDict({"internal": 0, "external": 0})
        events_by_coords: CounterDict = CounterDict()

        geoip_hits = 0
        geoip_misses = 0

        for entry in entries:
            events_by_geo[(entry.event, entry.country, entry.city)] += 1
            events_by_location[classify_ip(entry.ip)] += 1
            coords = self._lookup_coords(entry.ip)
            if self._geoip is not None:
                if coords is not None:
                    geoip_hits += 1
                    events_by_coords[(entry.country, entry.city, coords)] += 1
                else:
                    geoip_misses += 1

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
            if geoip_hits or geoip_misses:
                self._metrics.geoip_lookups.labels(result="hit").inc(geoip_hits)
                self._metrics.geoip_lookups.labels(result="miss").inc(geoip_misses)
                log.debug(
                    "GeoIP lookups: hits=%d misses=%d", geoip_hits, geoip_misses,
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

