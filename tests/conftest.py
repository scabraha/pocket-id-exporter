import pytest
from prometheus_client import CollectorRegistry

from pocket_id_exporter.config import Config
from pocket_id_exporter.metrics import Metrics


@pytest.fixture
def config() -> Config:
    return Config(
        pocket_id_url="http://pocket.test",
        api_key="test-key",
        poll_interval=1,
        request_timeout=5,
        page_size=2,
        audit_window_hours=24,
    )


@pytest.fixture
def metrics() -> Metrics:
    """Fresh metrics bound to a fresh registry per test."""
    return Metrics(CollectorRegistry())
