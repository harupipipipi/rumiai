from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


UNSAFE_SCHEMES = frozenset(
    {"javascript", "data", "file", "chrome", "about", "edge", "devtools"}
)

_SCHEME_RE = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):")
_LOCAL_TARGET_RE = re.compile(
    r"^(?P<host>localhost|127\.0\.0\.1)"
    r"(?::(?P<port>\d{1,5}))?"
    r"(?P<suffix>(?:/[^\s]*)?(?:\?[^\s]*)?(?:#[^\s]*)?)$",
    re.IGNORECASE,
)
_DOMAIN_RE = re.compile(
    r"^(?P<host>(?:[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63})"
    r"(?::(?P<port>\d{1,5}))?"
    r"(?P<suffix>(?:/[^\s]*)?(?:\?[^\s]*)?(?:#[^\s]*)?)$",
    re.IGNORECASE,
)


def unsafe_scheme_reason(raw: str) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    match = _SCHEME_RE.match(text)
    if not match:
        return None
    scheme = str(match.group("scheme") or "").lower()
    if scheme in UNSAFE_SCHEMES:
        return f"unsafe URL scheme is blocked: {scheme}:"
    return None


def classify_direct_url(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text or any(char.isspace() for char in text):
        return None

    local = _LOCAL_TARGET_RE.match(text)
    if local:
        port = _validated_port(local.group("port"))
        if local.group("port") and port is None:
            return None
        host = str(local.group("host") or "")
        suffix = str(local.group("suffix") or "")
        authority = host if port is None else f"{host}:{port}"
        return {
            "url": f"http://{authority}{suffix}",
            "scheme": "http",
            "reason": "recognized local development target",
        }

    blocked_reason = unsafe_scheme_reason(text)
    if blocked_reason:
        match = _SCHEME_RE.match(text)
        return {
            "blocked": True,
            "scheme": str(match.group("scheme") or "").lower() if match else "",
            "reason": blocked_reason,
        }

    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", text):
        parts = urlsplit(text)
        scheme = str(parts.scheme or "").lower()
        if scheme not in {"http", "https"} or not parts.netloc:
            return None
        normalized = urlunsplit(
            (
                scheme,
                parts.netloc,
                parts.path or "",
                parts.query or "",
                parts.fragment or "",
            )
        )
        return {
            "url": normalized,
            "scheme": scheme,
            "reason": "recognized absolute URL",
        }

    domain = _DOMAIN_RE.match(text)
    if domain:
        port = _validated_port(domain.group("port"))
        if domain.group("port") and port is None:
            return None
        host = str(domain.group("host") or "")
        suffix = str(domain.group("suffix") or "")
        authority = host if port is None else f"{host}:{port}"
        return {
            "url": f"https://{authority}{suffix}",
            "scheme": "https",
            "reason": "recognized domain target",
        }

    return None


def _validated_port(raw_port: str | None) -> int | None:
    if raw_port in (None, ""):
        return None
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        return None
    if 1 <= port <= 65535:
        return port
    return None
