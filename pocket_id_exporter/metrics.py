"""Prometheus metric definitions and small metric helpers."""

from __future__ import annotations

import ipaddress

from prometheus_client import CollectorRegistry, Counter, Gauge, Info

# Audit-log event names that count as user logins for the per-user metrics.
LOGIN_EVENTS = frozenset({"SIGN_IN", "TOKEN_SIGN_IN"})


class Metrics:
    """Container for all metrics the exporter exposes.

    Metrics are bound to an explicit registry so tests can use a fresh
    registry per test and avoid the global ``REGISTRY`` singleton.
    """

    def __init__(self, registry: CollectorRegistry):
        self.registry = registry

        # ---- counters (cumulative) ----
        self.audit_events = Counter(
            "pocketid_audit_events_total",
            "Total audit log events observed",
            ["event", "client_name"],
            registry=registry,
        )
        self.user_logins = Counter(
            "pocketid_user_logins_total",
            "User login events observed, by username and country",
            ["username", "country"],
            registry=registry,
        )
        self.user_new_country_logins = Counter(
            "pocketid_user_new_country_logins_total",
            "First time a user has been seen logging in from a given country",
            ["username", "country"],
            registry=registry,
        )

        # ---- inventory gauges ----
        self.users_total = Gauge(
            "pocketid_users_total",
            "Total registered users",
            registry=registry,
        )
        self.oidc_clients_total = Gauge(
            "pocketid_oidc_clients_total",
            "Total OIDC clients",
            registry=registry,
        )
        self.user_groups_total = Gauge(
            "pocketid_user_groups_total",
            "Total user groups",
            registry=registry,
        )

        # ---- recent-window gauges ----
        self.recent_events = Gauge(
            "pocketid_recent_events",
            "Audit events in the recent window, by event type, country, and city",
            ["event", "country", "city"],
            registry=registry,
        )
        self.events_by_location = Gauge(
            "pocketid_recent_events_by_location",
            "Audit events in the recent window by network location",
            ["location"],
            registry=registry,
        )
        self.event_geolocation = Gauge(
            "pocketid_event_geolocation",
            "Audit events in the recent window grouped by geo coordinates",
            ["country", "city", "latitude", "longitude"],
            registry=registry,
        )

        # ---- exporter self-monitoring ----
        self.poll_duration = Gauge(
            "pocketid_exporter_poll_duration_seconds",
            "Wall-clock duration of the most recent poll cycle",
            registry=registry,
        )
        self.poll_failures = Counter(
            "pocketid_exporter_poll_failures_total",
            "Total number of poll cycles that ended in failure",
            ["step"],
            registry=registry,
        )
        self.last_successful_poll = Gauge(
            "pocketid_exporter_last_successful_poll_timestamp_seconds",
            "Unix timestamp of the most recent successful poll cycle",
            registry=registry,
        )
        self.geoip_lookups = Counter(
            "pocketid_exporter_geoip_lookups_total",
            "GeoIP lookups attempted, by result (hit/miss)",
            ["result"],
            registry=registry,
        )

        # ---- meta ----
        self.version_info = Info(
            "pocketid_version",
            "Pocket-ID version information",
            registry=registry,
        )
        self.up = Gauge(
            "pocketid_up",
            "Whether the exporter can reach Pocket-ID",
            registry=registry,
        )


def classify_ip(ip: str) -> str:
    """Return ``"internal"`` for private/loopback/link-local IPs, else ``"external"``.

    Returns ``"unknown"`` for empty or unparseable input so we never emit
    a misleading label.
    """
    if not ip:
        return "unknown"
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        return "internal"
    return "external"

