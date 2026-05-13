# Pocket-ID Prometheus Exporter

A lightweight Prometheus exporter that polls the [Pocket-ID](https://github.com/pocket-id/pocket-id) admin API for audit logs, user counts, and OIDC client info.

Pocket-ID ships with OpenTelemetry infrastructure but currently exposes no application-level metrics. This exporter fills that gap by polling the REST API and exposing auth/SSO data as Prometheus metrics.

## Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `pocketid_audit_events_total` | Counter | `event`, `client_name` | Total audit log events by type |
| `pocketid_users_total` | Gauge | — | Total registered users |
| `pocketid_oidc_clients_total` | Gauge | — | Total OIDC clients |
| `pocketid_user_groups_total` | Gauge | — | Total user groups |
| `pocketid_recent_events_by_country` | Gauge | `country` | Audit events in the last 24h by country |
| `pocketid_recent_events_by_location` | Gauge | `location` | Audit events in the last 24h (internal/external) |
| `pocketid_version_info` | Info | `version` | Running Pocket-ID version |
| `pocketid_up` | Gauge | — | Whether the exporter can reach Pocket-ID |

### Audit event types

`SIGN_IN`, `TOKEN_SIGN_IN`, `ACCOUNT_CREATED`, `CLIENT_AUTHORIZATION`, `NEW_CLIENT_AUTHORIZATION`, `DEVICE_CODE_AUTHORIZATION`, `NEW_DEVICE_CODE_AUTHORIZATION`, `PASSKEY_ADDED`, `PASSKEY_REMOVED`

## Quick Start

### Docker Compose

```yaml
services:
  pocket-id-exporter:
    image: ghcr.io/scabraha/pocket-id-exporter:latest
    container_name: pocket-id-exporter
    restart: unless-stopped
    environment:
      - POCKET_ID_URL=http://pocket-id:1411
      - POCKET_ID_API_KEY=pk_your_api_key_here
    ports:
      - 9100:9100
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POCKET_ID_URL` | Yes | — | Base URL of the Pocket-ID instance |
| `POCKET_ID_API_KEY` | Yes | — | Admin-scoped API key (create in Pocket-ID UI) |
| `EXPORTER_PORT` | No | `9100` | Port to listen on |
| `POLL_INTERVAL` | No | `60` | Seconds between API polls |
| `LOG_LEVEL` | No | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

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

## Building

```bash
docker build -t pocket-id-exporter .
```

## License

MIT
