"""Prometheus metric definitions and small metric helpers."""

from __future__ import annotations

import ipaddress

from prometheus_client import CollectorRegistry, Counter, Gauge, Info


class Metrics:
    """Container for all metrics the exporter exposes.

    Metrics are bound to an explicit registry so tests can use a fresh
    registry per test and avoid the global ``REGISTRY`` singleton.
    """

    def __init__(self, registry: CollectorRegistry):
        self.registry = registry

        self.audit_events = Counter(
            "pocketid_audit_events_total",
            "Total audit log events observed",
            ["event", "client_name"],
            registry=registry,
        )
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
        self.events_by_country = Gauge(
            "pocketid_recent_events_by_country",
            "Audit events in the last N hours by country",
            ["country"],
            registry=registry,
        )
        self.events_by_location = Gauge(
            "pocketid_recent_events_by_location",
            "Audit events in the last N hours by network location",
            ["location"],
            registry=registry,
        )
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
