from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(item)
    for item in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def validate_egress_url(url: str, *, domains: tuple[str, ...], ports: tuple[int, ...]) -> bool:
    parsed = urlparse(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    if parsed.hostname not in set(domains):
        return False
    port = parsed.port or 443
    return port in set(ports or (443,))


def resolved_ip_allowed(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not any(ip in network for network in PRIVATE_NETWORKS)
