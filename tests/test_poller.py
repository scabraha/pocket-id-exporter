from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from pocket_id_exporter.poller import Poller


@pytest.fixture
def now():
    return datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def fake_client():
    client = MagicMock()
    client.version.return_value = "1.2.3"
    client.total_items.side_effect = lambda path: {
        "/api/users": 10,
        "/api/oidc/clients": 3,
        "/api/user-groups": 2,
    }[path]
    client.fetch_audit_logs_since.return_value = []
    return client


@pytest.fixture
def poller(fake_client, metrics, config, now):
    return Poller(fake_client, metrics, config, clock=lambda: now)


def _read_gauge(metric, **labels) -> float:
    """Read a gauge value, with or without labels."""
    if labels:
        return metric.labels(**labels)._value.get()
    return metric._value.get()


def _label_values(metric) -> dict:
    """Return {label_tuple: value} for a labelled metric."""
    return {
        labels: child._value.get()
        for labels, child in metric._metrics.items()
    }


def test_poll_once_updates_basic_metrics(poller, fake_client, metrics):
    poller.poll_once()

    assert _read_gauge(metrics.up) == 1
    assert _read_gauge(metrics.users_total) == 10
    assert _read_gauge(metrics.oidc_clients_total) == 3
    assert _read_gauge(metrics.user_groups_total) == 2
    assert metrics.version_info._value == {"version": "1.2.3"}


def test_poll_once_marks_down_on_failure(poller, fake_client, metrics):
    fake_client.version.side_effect = RuntimeError("boom")

    poller.poll_once()

    assert _read_gauge(metrics.up) == 0


def test_audit_event_counters_increment(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        {"createdAt": (now - timedelta(minutes=10)).isoformat(),
         "event": "SIGN_IN", "data": {"clientName": "app1"},
         "ipAddress": "8.8.8.8", "country": "US"},
        {"createdAt": (now - timedelta(minutes=5)).isoformat(),
         "event": "SIGN_IN", "data": {"clientName": "app1"},
         "ipAddress": "10.0.0.1", "country": "US"},
        {"createdAt": (now - timedelta(minutes=1)).isoformat(),
         "event": "PASSKEY_ADDED", "data": None,
         "ipAddress": "1.1.1.1", "country": "DE"},
    ]

    poller.poll_once()

    counter_values = _label_values(metrics.audit_events)
    assert counter_values[("SIGN_IN", "app1")] == 2
    assert counter_values[("PASSKEY_ADDED", "")] == 1


def test_geo_gauges_reflect_window(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        {"createdAt": (now - timedelta(minutes=1)).isoformat(),
         "event": "SIGN_IN", "data": {}, "ipAddress": "10.0.0.1", "country": "US"},
        {"createdAt": (now - timedelta(minutes=2)).isoformat(),
         "event": "SIGN_IN", "data": {}, "ipAddress": "1.1.1.1", "country": "DE"},
        {"createdAt": (now - timedelta(minutes=3)).isoformat(),
         "event": "SIGN_IN", "data": {}, "ipAddress": "1.1.1.1", "country": "DE"},
    ]

    poller.poll_once()

    countries = _label_values(metrics.events_by_country)
    assert countries[("US",)] == 1
    assert countries[("DE",)] == 2

    locations = _label_values(metrics.events_by_location)
    assert locations[("internal",)] == 1
    assert locations[("external",)] == 2


def test_geo_gauges_clear_between_polls(poller, fake_client, metrics, now):
    # First poll: one event from FR
    fake_client.fetch_audit_logs_since.return_value = [
        {"createdAt": (now - timedelta(minutes=1)).isoformat(),
         "event": "SIGN_IN", "data": {}, "ipAddress": "1.1.1.1", "country": "FR"},
    ]
    poller.poll_once()
    assert ("FR",) in _label_values(metrics.events_by_country)

    # Advance the clock 25h; FR event has aged out. Provide a fresh US event
    # that is within the new window.
    later = now + timedelta(hours=25)
    poller._clock = lambda: later
    fake_client.fetch_audit_logs_since.return_value = [
        {"createdAt": (later - timedelta(minutes=1)).isoformat(),
         "event": "SIGN_IN", "data": {}, "ipAddress": "1.1.1.1", "country": "US"},
    ]

    poller.poll_once()

    countries = _label_values(metrics.events_by_country)
    assert ("FR",) not in countries
    assert countries[("US",)] == 1


def test_only_new_events_increment_counter(poller, fake_client, metrics, now):
    # First poll seeds last_seen with some events.
    first_batch = [
        {"createdAt": (now - timedelta(minutes=10)).isoformat(),
         "event": "SIGN_IN", "data": {}, "ipAddress": "8.8.8.8", "country": "US"},
        {"createdAt": (now - timedelta(minutes=5)).isoformat(),
         "event": "SIGN_IN", "data": {}, "ipAddress": "8.8.8.8", "country": "US"},
    ]
    fake_client.fetch_audit_logs_since.return_value = first_batch
    poller.poll_once()

    first_count = _label_values(metrics.audit_events)[("SIGN_IN", "")]

    # Second poll: same two old events plus one new one. Only the new one counts.
    fake_client.fetch_audit_logs_since.return_value = first_batch + [
        {"createdAt": (now - timedelta(minutes=1)).isoformat(),
         "event": "SIGN_IN", "data": {}, "ipAddress": "8.8.8.8", "country": "US"},
    ]
    poller.poll_once()

    second_count = _label_values(metrics.audit_events)[("SIGN_IN", "")]
    assert second_count == first_count + 1


def test_country_unknown_when_missing(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        {"createdAt": (now - timedelta(minutes=1)).isoformat(),
         "event": "SIGN_IN", "data": {}, "ipAddress": "8.8.8.8", "country": None},
    ]
    poller.poll_once()
    assert _label_values(metrics.events_by_country)[("Unknown",)] == 1


def test_run_forever_stops_on_event(poller, fake_client):
    import threading
    stop = threading.Event()

    def stop_after_first(*args, **kwargs):
        stop.set()
        return []

    fake_client.fetch_audit_logs_since.side_effect = stop_after_first

    poller.run_forever(stop)
    # If we reach here, run_forever exited cleanly.
    assert stop.is_set()
