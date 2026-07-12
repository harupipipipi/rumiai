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
        "x-rumi-approval-browser-token",
        "x-rumi-principal",
        "x-rumi-profile",
        "x-rumi-client-principal",
    }
)

RESERVED_REQUEST_CONTEXT_KEYS = frozenset(
    {
        "_headers",
        "_authenticated_principal",
        "_authority_subject",
        "_method",
        "_actual_method",
        "_path",
        "_query_params",
        "_raw_body",
        "_raw_body_base64",
        "_browser_companion_bearer",
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


def strip_reserved_request_context(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    return {
        str(key): value
        for key, value in data.items()
        if str(key) not in RESERVED_REQUEST_CONTEXT_KEYS
    }
