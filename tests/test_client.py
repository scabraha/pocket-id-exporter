import pytest
import responses

from pocket_id_exporter.client import PocketIDClient


@pytest.fixture
def client() -> PocketIDClient:
    return PocketIDClient(
        base_url="http://pocket.test",
        api_key="test-key",
        timeout=5,
        page_size=2,
    )


@responses.activate
def test_get_sends_api_key_header(client):
    responses.get("http://pocket.test/api/ping", json={"ok": True})

    body = client.get("/api/ping")

    assert body == {"ok": True}
    assert responses.calls[0].request.headers["X-API-Key"] == "test-key"


@responses.activate
def test_total_items(client):
    responses.get(
        "http://pocket.test/api/users",
        json={"data": [], "pagination": {"totalItems": 42}},
    )
    assert client.total_items("/api/users") == 42


@responses.activate
def test_total_items_missing_field_returns_zero(client):
    responses.get("http://pocket.test/api/users", json={})
    assert client.total_items("/api/users") == 0


@responses.activate
def test_iter_audit_logs_paginates(client):
    responses.get(
        "http://pocket.test/api/audit-logs/all",
        json={
            "data": [{"id": 1}, {"id": 2}],
            "pagination": {"totalPages": 2},
        },
        match=[responses.matchers.query_param_matcher(
            {"pagination[page]": "1", "pagination[limit]": "2",
             "sort[column]": "createdAt", "sort[direction]": "asc"})],
    )
    responses.get(
        "http://pocket.test/api/audit-logs/all",
        json={
            "data": [{"id": 3}],
            "pagination": {"totalPages": 2},
        },
        match=[responses.matchers.query_param_matcher(
            {"pagination[page]": "2", "pagination[limit]": "2",
             "sort[column]": "createdAt", "sort[direction]": "asc"})],
    )

    ids = [e["id"] for e in client.iter_audit_logs()]

    assert ids == [1, 2, 3]


@responses.activate
def test_iter_audit_logs_stops_on_empty_page(client):
    responses.get(
        "http://pocket.test/api/audit-logs/all",
        json={"data": [], "pagination": {"totalPages": 5}},
    )
    assert list(client.iter_audit_logs()) == []


@responses.activate
def test_fetch_audit_logs_since_filters(client):
    responses.get(
        "http://pocket.test/api/audit-logs/all",
        json={
            "data": [
                {"createdAt": "2026-01-01T00:00:00Z", "id": 1},
                {"createdAt": "2026-01-02T00:00:00Z", "id": 2},
                {"createdAt": "2026-01-03T00:00:00Z", "id": 3},
            ],
            "pagination": {"totalPages": 1},
        },
    )
    result = client.fetch_audit_logs_since("2026-01-01T12:00:00Z")
    assert [e["id"] for e in result] == [2, 3]


@responses.activate
def test_version_string_response(client):
    responses.get("http://pocket.test/api/version/current", json="1.2.3")
    assert client.version() == "1.2.3"


@responses.activate
def test_version_dict_response(client):
    responses.get(
        "http://pocket.test/api/version/current",
        json={"version": "2.0.0"},
    )
    assert client.version() == "2.0.0"


@responses.activate
def test_version_unknown_when_missing(client):
    responses.get("http://pocket.test/api/version/current", json={})
    assert client.version() == "unknown"


@responses.activate
def test_get_raises_with_status_in_message(client):
    responses.get("http://pocket.test/api/users", status=403, body="forbidden")
    import requests
    with pytest.raises(requests.HTTPError) as exc_info:
        client.get("/api/users")
    msg = str(exc_info.value)
    assert "403" in msg
    assert "/api/users" in msg
    assert "POCKET_ID_API_KEY" in msg  # auth hint included


@responses.activate
def test_get_raises_includes_body_snippet(client):
    responses.get("http://pocket.test/api/users", status=500,
                  body="internal server error: db down")
    import requests
    with pytest.raises(requests.HTTPError) as exc_info:
        client.get("/api/users")
    assert "db down" in str(exc_info.value)


def test_base_url_strips_trailing_slash():
    c = PocketIDClient("http://pocket.test/", "k")
    assert c._base_url == "http://pocket.test"
