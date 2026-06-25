"""Helpers for forwarding HTTP headers to pack/runtime code."""

from __future__ import annotations

from typing import Any


SENSITIVE_FORWARDED_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "x-rumi-csrf",
        "x-rumi-approval",
        "x-rumi-approval-token",
        "x-rumi-principal",
        "x-rumi-profile",
        "x-rumi-client-principal",
    }
)


def sanitized_forwarded_headers(headers: Any) -> dict[str, str]:
    try:
        items = headers.items()
    except AttributeError:
        return {}
    result: dict[str, str] = {}
    for key, value in items:
        name = str(key)
        if name.lower() in SENSITIVE_FORWARDED_HEADERS:
            continue
        result[name] = str(value)
    return result
