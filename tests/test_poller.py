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


def _read_gauge(metric):
    return metric._value.get()


def _label_values(metric) -> dict:
    return {
        labels: child._value.get()
        for labels, child in metric._metrics.items()
    }


def _make_event(now, *, minutes_ago=1, event="SIGN_IN", username="alice",
                country="US", city="Seattle", ip="8.8.8.8", client_name=""):
    return {
        "createdAt": (now - timedelta(minutes=minutes_ago)).isoformat(),
        "event": event,
        "username": username,
        "country": country,
        "city": city,
        "ipAddress": ip,
        "data": {"clientName": client_name} if client_name else {},
    }


# -- inventory + up -------------------------------------------------------


def test_poll_once_updates_inventory(poller, metrics):
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


# -- cumulative counters --------------------------------------------------


def test_audit_event_counters_increment(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=10, event="SIGN_IN", client_name="app1"),
        _make_event(now, minutes_ago=5, event="SIGN_IN", client_name="app1"),
        _make_event(now, minutes_ago=1, event="PASSKEY_ADDED"),
    ]
    poller.poll_once()

    counters = _label_values(metrics.audit_events)
    assert counters[("SIGN_IN", "app1")] == 2
    assert counters[("PASSKEY_ADDED", "")] == 1


def test_only_new_events_increment_counter(poller, fake_client, metrics, now):
    first = [_make_event(now, minutes_ago=10), _make_event(now, minutes_ago=5)]
    fake_client.fetch_audit_logs_since.return_value = first
    poller.poll_once()
    first_count = _label_values(metrics.audit_events)[("SIGN_IN", "")]

    fake_client.fetch_audit_logs_since.return_value = first + [
        _make_event(now, minutes_ago=1)
    ]
    poller.poll_once()
    assert _label_values(metrics.audit_events)[("SIGN_IN", "")] == first_count + 1


# -- per-user login metrics ----------------------------------------------


def test_user_login_counter(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=10, username="alice", country="US"),
        _make_event(now, minutes_ago=5, username="alice", country="US"),
        _make_event(now, minutes_ago=1, username="bob", country="DE"),
    ]
    poller.poll_once()

    logins = _label_values(metrics.user_logins)
    assert logins[("alice", "US")] == 2
    assert logins[("bob", "DE")] == 1


def test_non_login_events_do_not_count_as_user_logins(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, event="PASSKEY_ADDED",
                    username="alice", country="US"),
    ]
    poller.poll_once()
    assert _label_values(metrics.user_logins) == {}


def test_login_without_username_is_skipped(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, username="", country="US"),
    ]
    poller.poll_once()
    assert _label_values(metrics.user_logins) == {}


def test_track_user_logins_can_be_disabled(fake_client, metrics, config, now):
    from dataclasses import replace
    cfg = replace(config, track_user_logins=False)
    poller = Poller(fake_client, metrics, cfg, clock=lambda: now)
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, username="alice", country="US"),
    ]
    poller.poll_once()
    assert _label_values(metrics.user_logins) == {}


def test_new_country_login_counter_fires_once_per_country(
    poller, fake_client, metrics, now
):
    # First poll: alice from US is new, then alice from DE is also new.
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=10, username="alice", country="US"),
        _make_event(now, minutes_ago=5, username="alice", country="DE"),
    ]
    poller.poll_once()
    new_country = _label_values(metrics.user_new_country_logins)
    assert new_country == {("alice", "US"): 1, ("alice", "DE"): 1}

    # Second poll: alice from US again should NOT fire new-country.
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, username="alice", country="US"),
    ]
    poller.poll_once()
    assert _label_values(metrics.user_new_country_logins) == {
        ("alice", "US"): 1,
        ("alice", "DE"): 1,
    }


def test_new_country_fires_for_unseen_country(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=10, username="alice", country="US"),
    ]
    poller.poll_once()

    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=10, username="alice", country="US"),
        _make_event(now, minutes_ago=1, username="alice", country="RU"),
    ]
    poller.poll_once()
    assert _label_values(metrics.user_new_country_logins)[("alice", "RU")] == 1


# -- recent-window gauges -------------------------------------------------


def test_recent_events_gauge_breaks_down_by_event_country_city(
    poller, fake_client, metrics, now
):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, event="SIGN_IN", country="US", city="Seattle"),
        _make_event(now, minutes_ago=2, event="SIGN_IN", country="US", city="Seattle"),
        _make_event(now, minutes_ago=3, event="PASSKEY_ADDED",
                    country="DE", city="Berlin"),
    ]
    poller.poll_once()

    values = _label_values(metrics.recent_events)
    assert values[("SIGN_IN", "US", "Seattle")] == 2
    assert values[("PASSKEY_ADDED", "DE", "Berlin")] == 1


def test_location_gauge_internal_external(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, ip="10.0.0.1"),
        _make_event(now, minutes_ago=2, ip="1.1.1.1"),
        _make_event(now, minutes_ago=3, ip="1.1.1.1"),
    ]
    poller.poll_once()
    locs = _label_values(metrics.events_by_location)
    assert locs[("internal",)] == 1
    assert locs[("external",)] == 2


def test_recent_events_gauge_clears_between_polls(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, country="FR", city="Paris"),
    ]
    poller.poll_once()
    assert ("SIGN_IN", "FR", "Paris") in _label_values(metrics.recent_events)

    later = now + timedelta(hours=25)
    poller._clock = lambda: later
    fake_client.fetch_audit_logs_since.return_value = [
        {"createdAt": (later - timedelta(minutes=1)).isoformat(),
         "event": "SIGN_IN", "country": "US", "city": "Seattle",
         "ipAddress": "1.1.1.1", "username": "bob", "data": {}},
    ]
    poller.poll_once()

    values = _label_values(metrics.recent_events)
    assert ("SIGN_IN", "FR", "Paris") not in values
    assert values[("SIGN_IN", "US", "Seattle")] == 1


def test_unknown_country_when_missing(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, country=None, city=None),
    ]
    poller.poll_once()
    values = _label_values(metrics.recent_events)
    assert values[("SIGN_IN", "Unknown", "Unknown")] == 1


# -- geolocation gauge ----------------------------------------------------


def test_geolocation_gauge_emitted_when_geoip_present(
    fake_client, metrics, config, now
):
    geoip = MagicMock()
    geoip.lookup.side_effect = lambda ip: {
        "8.8.8.8": (47.6, -122.3),
        "1.1.1.1": (51.5, -0.12),
    }.get(ip)

    poller = Poller(fake_client, metrics, config, geoip=geoip, clock=lambda: now)
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, country="US", city="Seattle", ip="8.8.8.8"),
        _make_event(now, minutes_ago=2, country="US", city="Seattle", ip="8.8.8.8"),
        _make_event(now, minutes_ago=3, country="GB", city="London", ip="1.1.1.1"),
    ]
    poller.poll_once()

    values = _label_values(metrics.event_geolocation)
    assert values[("US", "Seattle", "47.6000", "-122.3000")] == 2
    assert values[("GB", "London", "51.5000", "-0.1200")] == 1


def test_geolocation_gauge_skipped_when_no_geoip(poller, fake_client, metrics, now):
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, ip="8.8.8.8"),
    ]
    poller.poll_once()
    assert _label_values(metrics.event_geolocation) == {}


def test_geolocation_gauge_skips_unknown_ips(fake_client, metrics, config, now):
    geoip = MagicMock()
    geoip.lookup.return_value = None
    poller = Poller(fake_client, metrics, config, geoip=geoip, clock=lambda: now)
    fake_client.fetch_audit_logs_since.return_value = [
        _make_event(now, minutes_ago=1, ip="10.0.0.1"),
    ]
    poller.poll_once()
    assert _label_values(metrics.event_geolocation) == {}


# -- shutdown -------------------------------------------------------------


def test_run_forever_stops_on_event(poller, fake_client):
    import threading
    stop = threading.Event()

    def stop_after_first(*args, **kwargs):
        stop.set()
        return []

    fake_client.fetch_audit_logs_since.side_effect = stop_after_first
    poller.run_forever(stop)
    assert stop.is_set()
