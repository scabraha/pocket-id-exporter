"""CLI entry point: ``python -m pocket_id_exporter``."""

from __future__ import annotations

import logging
import signal
import sys
import threading

from prometheus_client import REGISTRY, start_http_server

from . import __version__
from .client import PocketIDClient
from .config import Config, ConfigError
from .geoip import GeoIPLookup
from .logging_setup import setup_logging
from .metrics import Metrics
from .poller import Poller

log = logging.getLogger("pocket_id_exporter")


def main() -> int:
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    setup_logging(level=config.log_level, fmt=config.log_format)

    log.info("pocket-id-exporter v%s starting", __version__)
    log.info("Effective config: %s", config.sanitized())

    client = PocketIDClient(
        base_url=config.pocket_id_url,
        api_key=config.api_key,
        timeout=config.request_timeout,
        page_size=config.page_size,
    )
    metrics = Metrics(REGISTRY)

    geoip = None
    if config.geoip_db_path:
        try:
            geoip = GeoIPLookup(config.geoip_db_path)
        except FileNotFoundError:
            log.error(
                "GeoIP database not found at %s; geolocation metrics disabled",
                config.geoip_db_path,
            )
        except Exception:
            log.exception(
                "Failed to load GeoIP database at %s; geolocation metrics disabled",
                config.geoip_db_path,
            )
    else:
        log.info("GEOIP_DB_PATH unset; lat/lon metrics disabled")

    poller = Poller(client, metrics, config, geoip=geoip)

    stop_event = threading.Event()

    def _shutdown(signum, _frame):
        log.info("Received signal %d, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        start_http_server(config.exporter_port)
    except OSError:
        log.exception("Failed to bind metrics server on port %d", config.exporter_port)
        return 1
    log.info("Metrics endpoint listening on :%d/metrics", config.exporter_port)

    poller.run_forever(stop_event)
    if geoip is not None:
        geoip.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())


