import pytest

from pocket_id_exporter.config import Config, ConfigError


def test_from_env_minimal():
    cfg = Config.from_env({
        "POCKET_ID_URL": "http://pocket:1411/",
        "POCKET_ID_API_KEY": "pk_test",
    })
    assert cfg.pocket_id_url == "http://pocket:1411"  # trailing slash stripped
    assert cfg.api_key == "pk_test"
    assert cfg.exporter_port == 9100
    assert cfg.poll_interval == 60
    assert cfg.log_level == "INFO"


def test_from_env_overrides():
    cfg = Config.from_env({
        "POCKET_ID_URL": "http://pocket:1411",
        "POCKET_ID_API_KEY": "pk_test",
        "EXPORTER_PORT": "8080",
        "POLL_INTERVAL": "10",
        "REQUEST_TIMEOUT": "5",
        "LOG_LEVEL": "debug",
        "PAGE_SIZE": "50",
        "AUDIT_WINDOW_HOURS": "48",
        "GEOIP_DB_PATH": "/etc/geoip/GeoLite2-City.mmdb",
        "TRACK_USER_LOGINS": "false",
    })
    assert cfg.exporter_port == 8080
    assert cfg.poll_interval == 10
    assert cfg.request_timeout == 5
    assert cfg.log_level == "DEBUG"
    assert cfg.page_size == 50
    assert cfg.audit_window_hours == 48
    assert cfg.geoip_db_path == "/etc/geoip/GeoLite2-City.mmdb"
    assert cfg.track_user_logins is False


def test_track_user_logins_default_true():
    cfg = Config.from_env({
        "POCKET_ID_URL": "http://pocket:1411",
        "POCKET_ID_API_KEY": "pk_test",
    })
    assert cfg.track_user_logins is True
    assert cfg.geoip_db_path == ""


def test_invalid_bool_raises():
    from pocket_id_exporter.config import ConfigError
    import pytest
    with pytest.raises(ConfigError, match="TRACK_USER_LOGINS"):
        Config.from_env({
            "POCKET_ID_URL": "http://pocket",
            "POCKET_ID_API_KEY": "k",
            "TRACK_USER_LOGINS": "maybe",
        })


def test_missing_url_raises():
    with pytest.raises(ConfigError, match="POCKET_ID_URL"):
        Config.from_env({"POCKET_ID_API_KEY": "x"})


def test_missing_api_key_raises():
    with pytest.raises(ConfigError, match="POCKET_ID_API_KEY"):
        Config.from_env({"POCKET_ID_URL": "http://x"})


def test_invalid_int_raises():
    with pytest.raises(ConfigError, match="EXPORTER_PORT"):
        Config.from_env({
            "POCKET_ID_URL": "http://pocket",
            "POCKET_ID_API_KEY": "k",
            "EXPORTER_PORT": "not-a-number",
        })


def test_blank_int_uses_default():
    cfg = Config.from_env({
        "POCKET_ID_URL": "http://pocket",
        "POCKET_ID_API_KEY": "k",
        "EXPORTER_PORT": "",
    })
    assert cfg.exporter_port == 9100
