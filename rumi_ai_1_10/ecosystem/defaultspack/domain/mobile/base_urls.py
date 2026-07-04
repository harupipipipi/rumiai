from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


_LOOPBACK_HOSTS = {"", "localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}


def is_loopback_host(host: str) -> bool:
    value = str(host or "").strip().strip("[]").lower()
    if value in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def normalize_mobile_base_url(value: str, *, allow_cleartext: bool = False) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        default_scheme = "http" if allow_cleartext else "https"
        parsed = urlsplit(raw if "://" in raw else f"{default_scheme}://{raw}")
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.scheme == "http" and not allow_cleartext:
        return ""
    host = parsed.hostname or ""
    if is_loopback_host(host):
        return ""
    netloc = parsed.netloc
    if ":" in host and not netloc.startswith("["):
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"[{host}]{port}"
    return f"{parsed.scheme}://{netloc}".rstrip("/")


def mobile_base_urls_from_headers(
    headers: dict[str, str] | None,
    *,
    local_addresses: list[str] | None = None,
    allow_cleartext: bool = False,
) -> list[str]:
    headers = headers or {}
    host_header = str(headers.get("Host") or headers.get("host") or "").strip()
    forwarded_proto = str(headers.get("X-Forwarded-Proto") or headers.get("x-forwarded-proto") or "").strip()
    scheme = "https" if forwarded_proto == "https" else "http"
    candidates: list[str] = []
    if host_header:
        candidates.append(f"{scheme}://{host_header}")

    port = _host_port(host_header, default=443 if scheme == "https" else 80)
    for address in local_addresses if local_addresses is not None else _local_lan_addresses():
        if _is_mobile_reachable_address(address):
            candidates.append(_format_origin(scheme, address, port))

    urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_mobile_base_url(candidate, allow_cleartext=allow_cleartext)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def _host_port(host_header: str, *, default: int) -> int:
    try:
        parsed = urlsplit(f"http://{host_header}")
        return int(parsed.port or default)
    except ValueError:
        return default


def _format_origin(scheme: str, host: str, port: int) -> str:
    try:
        ip = ipaddress.ip_address(str(host).strip())
        formatted = f"[{ip.compressed}]" if ip.version == 6 else ip.compressed
    except ValueError:
        formatted = str(host).strip()
    default_port = 443 if scheme == "https" else 80
    return f"{scheme}://{formatted}" if port == default_port else f"{scheme}://{formatted}:{port}"


def _is_mobile_reachable_address(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(str(value).strip())
    except ValueError:
        return False
    return not ip.is_loopback and (ip.is_private or ip.is_link_local)


def _local_lan_addresses() -> list[str]:
    addresses: set[str] = set()
    for host in {socket.gethostname(), socket.getfqdn()}:
        if not host:
            continue
        try:
            for family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(host, None):
                if family in {socket.AF_INET, socket.AF_INET6} and sockaddr:
                    addresses.add(str(sockaddr[0]))
        except OSError:
            pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            addresses.add(str(sock.getsockname()[0]))
    except OSError:
        pass

    return sorted(addresses)
