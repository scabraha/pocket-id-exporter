from pocket_id_exporter.audit import AuditEntry


def test_from_api_full_payload():
    entry = AuditEntry.from_api({
        "createdAt": "2026-05-13T10:00:00Z",
        "event": "SIGN_IN",
        "username": "alice",
        "country": "United States",
        "city": "Seattle",
        "ipAddress": "8.8.8.8",
        "data": {"clientName": "grafana"},
    })
    assert entry.created_at == "2026-05-13T10:00:00Z"
    assert entry.event == "SIGN_IN"
    assert entry.username == "alice"
    assert entry.country == "United States"
    assert entry.city == "Seattle"
    assert entry.ip == "8.8.8.8"
    assert entry.client_name == "grafana"
    assert entry.is_login is True


def test_from_api_minimal_payload_uses_defaults():
    entry = AuditEntry.from_api({})
    assert entry.created_at == ""
    assert entry.event == "UNKNOWN"
    assert entry.username == ""
    assert entry.country == "Unknown"
    assert entry.city == "Unknown"
    assert entry.ip == ""
    assert entry.client_name == ""
    assert entry.is_login is False


def test_from_api_null_data_is_safe():
    entry = AuditEntry.from_api({"event": "SIGN_IN", "data": None})
    assert entry.client_name == ""


def test_from_api_null_country_falls_back_to_unknown():
    entry = AuditEntry.from_api({"country": None, "city": None, "ipAddress": None})
    assert entry.country == "Unknown"
    assert entry.city == "Unknown"
    assert entry.ip == ""


def test_token_sign_in_is_login():
    assert AuditEntry.from_api({"event": "TOKEN_SIGN_IN"}).is_login is True


def test_passkey_added_is_not_login():
    assert AuditEntry.from_api({"event": "PASSKEY_ADDED"}).is_login is False
