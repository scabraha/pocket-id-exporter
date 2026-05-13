"""CLI entry point: ``python -m pocket_id_exporter``."""

from __future__ import annotations

import logging
import signal
import sys
import threading

from prometheus_client import REGISTRY, start_http_server

from .client import PocketIDClient
from .config import Config, ConfigError
from .geoip import GeoIPLookup
from .metrics import Metrics
from .poller import Poller

log = logging.getLogger("pocket_id_exporter")


def main() -> int:
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    log.info(
        "Starting Pocket-ID exporter on :%d (poll every %ds, target=%s)",
        config.exporter_port,
        config.poll_interval,
        config.pocket_id_url,
    )

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
        except Exception:
            log.exception(
                "Failed to load GeoIP database at %s; geolocation metrics disabled",
                config.geoip_db_path,
            )

    poller = Poller(client, metrics, config, geoip=geoip)

    stop_event = threading.Event()

    def _shutdown(signum, _frame):
        log.info("Received signal %d, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    start_http_server(config.exporter_port)
    poller.run_forever(stop_event)
    return 0


if __name__ == "__main__":
    sys.exit(main())

