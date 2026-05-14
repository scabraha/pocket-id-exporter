# Changelog

## [1.1.1](https://github.com/scabraha/pocket-id-exporter/compare/v1.1.0...v1.1.1) (2026-05-14)


### Bug Fixes

* **deps:** update dependency maxminddb to v2.8.2 ([b5916ee](https://github.com/scabraha/pocket-id-exporter/commit/b5916ee1af5c0d149099890198781d46b0276b49))
* **deps:** update dependency maxminddb to v2.8.2 ([69fb64f](https://github.com/scabraha/pocket-id-exporter/commit/69fb64f096ece2bf0750be32467384a5c74da7f8))
* **deps:** update dependency maxminddb to v3 ([0b38371](https://github.com/scabraha/pocket-id-exporter/commit/0b383713f310d160976512f807cfbbcadb2acb19))
* **deps:** update dependency maxminddb to v3 ([d2219cb](https://github.com/scabraha/pocket-id-exporter/commit/d2219cb1d3e94e06ec9f8db860c8cbe9c531ecc2))
* **deps:** update dependency prometheus-client to v0.25.0 ([bfe4613](https://github.com/scabraha/pocket-id-exporter/commit/bfe46130a146c198cf983576fb9353c58828f798))
* **deps:** update dependency prometheus-client to v0.25.0 ([6a5a83f](https://github.com/scabraha/pocket-id-exporter/commit/6a5a83f62624faea7efd14f07a575954a1334d21))
* **deps:** update dependency requests to v2.34.1 ([6c729da](https://github.com/scabraha/pocket-id-exporter/commit/6c729daf08a4f367af27a512fc26587bfcbeeeaf))
* **deps:** update dependency requests to v2.34.1 ([ff2b956](https://github.com/scabraha/pocket-id-exporter/commit/ff2b956be9c1d37e55c48e7c639ac6d06e89c3d4))

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
