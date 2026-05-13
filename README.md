# Pocket-ID Prometheus Exporter

A lightweight Prometheus exporter that polls the [Pocket-ID](https://github.com/pocket-id/pocket-id) admin API for audit logs, user counts, and OIDC client info.

Pocket-ID ships with OpenTelemetry infrastructure but currently exposes no application-level metrics. This exporter fills that gap by polling the REST API and exposing auth/SSO data as Prometheus metrics.

## Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `pocketid_audit_events_total` | Counter | `event`, `client_name` | Total audit log events by type and OIDC client |
| `pocketid_user_logins_total` | Counter | `username`, `country` | Login events by user and source country |
| `pocketid_user_new_country_logins_total` | Counter | `username`, `country` | Increments the first time a user logs in from a given country (security signal) |
| `pocketid_users_total` | Gauge | — | Total registered users |
| `pocketid_oidc_clients_total` | Gauge | — | Total OIDC clients |
| `pocketid_user_groups_total` | Gauge | — | Total user groups |
| `pocketid_recent_events` | Gauge | `event`, `country`, `city` | Audit events in the recent window broken down by event type and location |
| `pocketid_recent_events_by_location` | Gauge | `location` | Audit events in the recent window (`internal` / `external` / `unknown`) |
| `pocketid_event_geolocation` | Gauge | `country`, `city`, `latitude`, `longitude` | Audit events in the recent window grouped by geo coordinates (only when `GEOIP_DB_PATH` is set) |
| `pocketid_version_info` | Info | `version` | Running Pocket-ID version |
| `pocketid_up` | Gauge | — | Whether the exporter can reach Pocket-ID |

> Country/city come straight from Pocket-ID (it does GeoIP itself). Latitude/longitude require mounting a MaxMind GeoLite2-City database — see [GeoIP](#geoip) below.

### Audit event types

`SIGN_IN`, `TOKEN_SIGN_IN`, `ACCOUNT_CREATED`, `CLIENT_AUTHORIZATION`, `NEW_CLIENT_AUTHORIZATION`, `DEVICE_CODE_AUTHORIZATION`, `NEW_DEVICE_CODE_AUTHORIZATION`, `PASSKEY_ADDED`, `PASSKEY_REMOVED`. `SIGN_IN` and `TOKEN_SIGN_IN` are treated as "logins" for the per-user counters.

## Quick Start

### Docker Compose

```yaml
services:
  pocket-id-exporter:
    image: ghcr.io/scabraha/pocket-id-exporter:latest
    container_name: pocket-id-exporter
    restart: unless-stopped
    env_file: .env
    ports:
      - 9100:9100
```

`.env`:

```env
POCKET_ID_URL=http://pocket-id:1411
POCKET_ID_API_KEY=pk_your_api_key_here
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POCKET_ID_URL` | Yes | — | Base URL of the Pocket-ID instance |
| `POCKET_ID_API_KEY` | Yes | — | Admin-scoped API key (create in Pocket-ID UI) |
| `EXPORTER_PORT` | No | `9100` | Port to listen on |
| `POLL_INTERVAL` | No | `60` | Seconds between API polls |
| `REQUEST_TIMEOUT` | No | `30` | HTTP request timeout (seconds) |
| `PAGE_SIZE` | No | `100` | Audit log page size |
| `AUDIT_WINDOW_HOURS` | No | `24` | Window for the `recent_events*` gauges |
| `TRACK_USER_LOGINS` | No | `true` | Emit per-user login counters (set `false` for very high user counts) |
| `GEOIP_DB_PATH` | No | — | Path to a MaxMind GeoLite2-City `.mmdb` file. Enables `pocketid_event_geolocation`. |
| `LOG_LEVEL` | No | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## GeoIP

`country` and `city` labels are populated by Pocket-ID itself, so they work without any extra setup.

For latitude/longitude (e.g. for a Grafana world-map panel), mount a MaxMind [GeoLite2-City](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) database and point `GEOIP_DB_PATH` at it:

```yaml
services:
  pocket-id-exporter:
    image: ghcr.io/scabraha/pocket-id-exporter:latest
    env_file: .env
    volumes:
      - ./GeoLite2-City.mmdb:/geoip/GeoLite2-City.mmdb:ro
    ports:
      - 9100:9100
```

`.env`:

```env
GEOIP_DB_PATH=/geoip/GeoLite2-City.mmdb
```

If the file is missing or corrupt, geolocation metrics are silently disabled — the rest of the exporter keeps running.

### Cardinality notes

`pocketid_user_logins_total` and `pocketid_user_new_country_logins_total` carry a `username` label. For typical Pocket-ID deployments (tens to low hundreds of users) this is fine. If you have thousands of users, set `TRACK_USER_LOGINS=false` to suppress them.

`pocketid_user_new_country_logins_total` tracks "new country" relative to **this exporter process**: a restart re-seeds the seen-countries set, so the first login per (user, country) after a restart will fire the counter again.

## Creating an API Key

1. Log into Pocket-ID as an admin
2. Go to your profile → API Keys
3. Create a new key with a descriptive name (e.g. "prometheus-exporter")
4. Copy the token — it's only shown once

> **Note:** The API key must belong to an admin user to access `/api/audit-logs/all`, `/api/users`, `/api/oidc/clients`, and `/api/user-groups`.

## Prometheus Scrape Config

```yaml
scrape_configs:
  - job_name: "pocket-id-exporter"
    static_configs:
      - targets: ["pocket-id-exporter:9100"]
```

## Building & Testing

```bash
# Run tests
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest

# Build container image
docker build -t pocket-id-exporter .
```

## Releases

Releases are automated by [release-please](https://github.com/googleapis/release-please) using [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` → minor bump
- `fix:` / `perf:` → patch bump
- `feat!:` or `BREAKING CHANGE:` footer → major bump

On each push to `main`, release-please opens or updates a release PR with the new version and changelog. Merging it tags the release and publishes a multi-arch (`linux/amd64`, `linux/arm64`) image to `ghcr.io/scabraha/pocket-id-exporter` with tags `vX.Y.Z`, `X.Y`, `X`, and `latest`.

## License

MIT
