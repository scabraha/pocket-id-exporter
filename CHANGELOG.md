# Changelog

## [1.1.0](https://github.com/scabraha/pocket-id-exporter/compare/v1.0.0...v1.1.0) (2026-05-13)


### Features

* production-grade logging, structured output, and self-monitoring metrics ([68905c4](https://github.com/scabraha/pocket-id-exporter/commit/68905c424c86ed156b61c8ca3ec2ebcefc1f8b15))

## [1.0.0](https://github.com/scabraha/pocket-id-exporter/compare/v0.3.0...v1.0.0) (2026-05-13)


### ⚠ BREAKING CHANGES

* pocketid_recent_events_by_country{country} has been removed; use pocketid_recent_events{event, country, city} (sum by (country) for the old behaviour). Adds maxminddb to runtime dependencies (~50 KB pure-Python).

### Features

* rich geolocation metrics and audit-log refactor ([ba2bdd1](https://github.com/scabraha/pocket-id-exporter/commit/ba2bdd1575c2ff940bde068cf5c330312a5a55d1))

## [0.3.0](https://github.com/scabraha/pocket-id-exporter/compare/v0.2.0...v0.3.0) (2026-05-13)


### ⚠ BREAKING CHANGES

* entry point is now 'python -m pocket_id_exporter' (or the 'pocket-id-exporter' console script); 'python exporter.py' no longer exists.

### Features

* initial Pocket-ID Prometheus exporter ([8b88f3d](https://github.com/scabraha/pocket-id-exporter/commit/8b88f3dbc6e00a748148468fefe329c81d155796))
* restructure into pocket_id_exporter package with tests ([cff9972](https://github.com/scabraha/pocket-id-exporter/commit/cff99726e019dae99abc79241446f3ffbc1da542))
