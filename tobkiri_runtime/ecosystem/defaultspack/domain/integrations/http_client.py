from __future__ import annotations

import contextlib
import ipaddress
import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable


_GETADDRINFO_LOCK = threading.Lock()


class PublicUrlError(ValueError):
    """Raised when a caller-controlled URL is not safe for outbound webhook egress."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise PublicUrlError("redirects are not allowed for caller-controlled webhook URLs")


def post_json(
    url: str, headers: Dict[str, str], payload: Dict[str, Any], *, timeout: float = 10.0
) -> Dict[str, Any]:
    return _post_json(
        url, headers, payload, timeout=timeout, include_response_body=True, opener=None
    )


def post_json_public_url(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    *,
    timeout: float = 10.0,
    allowed_hosts: Iterable[str] | None = None,
    allowed_host_suffixes: Iterable[str] | None = None,
    include_response_body: bool = False,
) -> Dict[str, Any]:
    """POST JSON to a caller-controlled public HTTPS URL.

    This helper is intended for webhooks/callbacks supplied by users or models. It
    rejects non-HTTPS URLs, private/loopback/link-local DNS answers, and redirects,
    then suppresses response bodies by default so internal services cannot be used
    as an exfiltration channel in tool results.
    """

    try:
        host, addrinfo = _validate_public_https_url(
            url,
            allowed_hosts=allowed_hosts,
            allowed_host_suffixes=allowed_host_suffixes,
        )
    except PublicUrlError as exc:
        return {"ok": False, "status": 0, "body": {"error": str(exc)}}

    opener = urllib.request.build_opener(_NoRedirectHandler)
    with _pin_getaddrinfo(host, addrinfo):
        return _post_json(
            url,
            headers,
            payload,
            timeout=timeout,
            include_response_body=include_response_body,
            opener=opener,
        )


def _post_json(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    *,
    timeout: float,
    include_response_body: bool,
    opener: urllib.request.OpenerDirector | None,
) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8", **headers},
        method="POST",
    )
    open_request = opener.open if opener is not None else urllib.request.urlopen
    try:
        with open_request(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace") if include_response_body else ""
            parsed = _parse_response_body(raw) if include_response_body else {}
            return {"ok": 200 <= response.status < 300, "status": response.status, "body": parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if include_response_body else ""
        return {
            "ok": False,
            "status": exc.code,
            "body": _parse_response_body(raw) if include_response_body else {},
        }
    except PublicUrlError as exc:
        return {"ok": False, "status": 0, "body": {"error": str(exc)}}
    except Exception as exc:
        return {"ok": False, "status": 0, "body": {"error": str(exc)}}


def _parse_response_body(raw: str) -> Any:
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"body": raw}
    return parsed


def _validate_public_https_url(
    url: str,
    *,
    allowed_hosts: Iterable[str] | None = None,
    allowed_host_suffixes: Iterable[str] | None = None,
) -> tuple[str, list[tuple[Any, ...]]]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise PublicUrlError("webhook URL must use https")
    if parsed.username or parsed.password:
        raise PublicUrlError("webhook URL must not include credentials")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise PublicUrlError("webhook URL must include a host")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise PublicUrlError("webhook URL port is invalid") from exc
    if port != 443:
        raise PublicUrlError("webhook URL must use the default https port")
    if not _host_allowed(host, allowed_hosts, allowed_host_suffixes):
        raise PublicUrlError("webhook URL host is not allowed")

    try:
        addrinfo = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise PublicUrlError("webhook URL host could not be resolved") from exc
    if not addrinfo:
        raise PublicUrlError("webhook URL host could not be resolved")
    for item in addrinfo:
        sockaddr = item[4]
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_global:
            raise PublicUrlError("webhook URL host must resolve only to public addresses")
    return host, addrinfo


def _host_allowed(
    host: str,
    allowed_hosts: Iterable[str] | None,
    allowed_host_suffixes: Iterable[str] | None,
) -> bool:
    exact_hosts = {item.rstrip(".").lower() for item in (allowed_hosts or []) if item}
    suffixes = {item.rstrip(".").lower() for item in (allowed_host_suffixes or []) if item}
    if not exact_hosts and not suffixes:
        return True
    if host in exact_hosts:
        return True
    return any(host.endswith("." + suffix) for suffix in suffixes)


@contextlib.contextmanager
def _pin_getaddrinfo(host: str, addrinfo: list[tuple[Any, ...]]):
    """Pin the already-vetted address set for urllib's connection attempt."""

    original_getaddrinfo = socket.getaddrinfo

    def pinned_getaddrinfo(query_host, *args, **kwargs):  # type: ignore[no-untyped-def]
        if str(query_host).rstrip(".").lower() == host:
            return addrinfo
        return original_getaddrinfo(query_host, *args, **kwargs)

    with _GETADDRINFO_LOCK:
        socket.getaddrinfo = pinned_getaddrinfo  # type: ignore[assignment]
        try:
            yield
        finally:
            socket.getaddrinfo = original_getaddrinfo  # type: ignore[assignment]
