from unittest.mock import MagicMock

import pytest

from pocket_id_exporter.geoip import GeoIPLookup


@pytest.fixture
def fake_reader(monkeypatch):
    reader = MagicMock()

    def fake_open(_path):
        return reader

    fake_module = MagicMock()
    fake_module.open_database.side_effect = fake_open
    monkeypatch.setitem(__import__("sys").modules, "maxminddb", fake_module)
    return reader


def test_lookup_returns_lat_lon(fake_reader):
    fake_reader.get.return_value = {
        "location": {"latitude": 47.6062, "longitude": -122.3321}
    }
    geo = GeoIPLookup("/dev/null")
    assert geo.lookup("8.8.8.8") == (47.6062, -122.3321)


def test_lookup_returns_none_for_empty_ip(fake_reader):
    fake_reader.get.return_value = None
    geo = GeoIPLookup("/dev/null")
    assert geo.lookup("") is None


def test_lookup_returns_none_when_record_missing(fake_reader):
    fake_reader.get.return_value = None
    geo = GeoIPLookup("/dev/null")
    assert geo.lookup("8.8.8.8") is None


def test_lookup_returns_none_when_location_missing(fake_reader):
    fake_reader.get.return_value = {"city": {"names": {"en": "Seattle"}}}
    geo = GeoIPLookup("/dev/null")
    assert geo.lookup("8.8.8.8") is None


def test_lookup_returns_none_when_coords_partial(fake_reader):
    fake_reader.get.return_value = {"location": {"latitude": 1.0}}
    geo = GeoIPLookup("/dev/null")
    assert geo.lookup("8.8.8.8") is None


def test_lookup_returns_none_when_reader_raises(fake_reader):
    fake_reader.get.side_effect = ValueError("bad ip")
    geo = GeoIPLookup("/dev/null")
    assert geo.lookup("not-an-ip") is None
