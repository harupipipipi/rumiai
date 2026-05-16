from __future__ import annotations

import ipaddress
import urllib.parse
from typing import Any


LOCAL_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "::1"}

SENSITIVE_CODING_PATHS = {
    "/api/coding/files/write",
    "/api/coding/files/create",
    "/api/coding/files/delete",
    "/api/coding/files/patch",
    "/api/coding/files/snapshot",
    "/api/coding/files/restore",
    "/api/coding/terminal/exec",
    "/api/coding/terminal/stream",
    "/api/coding/git/commit",
    "/api/coding/git/push",
    "/api/coding/approvals/approve",
    "/api/coding/approvals/deny",
    "/api/coding/workspaces/update",
    "/api/coding/workspaces/select",
    "/api/coding/workspaces/trust",
}

METHOD_SENSITIVE_CODING_PATHS = {
    "/api/coding/git/branch": {"POST"},
    "/api/coding/workspaces": {"POST"},
}


def is_loopback_request(headers: dict[str, Any] | None = None, client_address: Any = None) -> bool:
    del headers
    host = ""
    if isinstance(client_address, (list, tuple)) and client_address:
        host = str(client_address[0])
    elif client_address:
        host = str(client_address)
    if not host:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in LOCAL_ORIGIN_HOSTS


def origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    try:
        parsed = urllib.parse.urlsplit(origin)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = parsed.hostname or ""
    if hostname in LOCAL_ORIGIN_HOSTS:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def csrf_required(method: str, origin: str | None) -> bool:
    return str(method or "").upper() in {"POST", "PUT", "DELETE"} and bool(origin)


def is_sensitive_coding_path(path: str, method: str | None = None) -> bool:
    normalized_path = str(path)
    if normalized_path in SENSITIVE_CODING_PATHS:
        return True
    methods = METHOD_SENSITIVE_CODING_PATHS.get(normalized_path)
    if not methods:
        return False
    if method is None:
        return True
    return str(method or "").upper() in methods


def require_local_guard(
    path: str,
    method: str,
    headers: dict[str, Any] | None,
    client_address: Any = None,
) -> tuple[int, str, str] | None:
    if not is_sensitive_coding_path(path, method):
        return None
    headers = headers or {}
    if not is_loopback_request(headers, client_address):
        return (403, "coding mutation requires a loopback client", "LOCAL_ONLY_REQUIRED")
    origin = str(headers.get("Origin", "") or "")
    if not origin_allowed(origin):
        return (403, "origin not allowed for sensitive coding route", "ORIGIN_DENIED")
    if csrf_required(method, origin) and not str(headers.get("X-Rumi-CSRF", "") or "").strip():
        return (403, "CSRF header required for sensitive coding mutation", "CSRF_REQUIRED")
    return None
