import pytest

from pocket_id_exporter.metrics import classify_ip


@pytest.mark.parametrize("ip,expected", [
    ("10.0.0.1", "internal"),
    ("172.16.0.5", "internal"),
    ("172.31.255.254", "internal"),
    ("192.168.1.10", "internal"),
    ("127.0.0.1", "internal"),
    ("169.254.1.1", "internal"),  # link-local
    ("::1", "internal"),  # IPv6 loopback
    ("fc00::1", "internal"),  # IPv6 ULA
    ("fe80::1", "internal"),  # IPv6 link-local
    ("8.8.8.8", "external"),
    ("1.1.1.1", "external"),
    ("2606:4700:4700::1111", "external"),
    ("172.32.0.1", "external"),  # outside RFC1918
    ("", "unknown"),
    ("not-an-ip", "unknown"),
    ("999.999.999.999", "unknown"),
])
def test_classify_ip(ip, expected):
    assert classify_ip(ip) == expected
