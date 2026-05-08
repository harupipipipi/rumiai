"""UI clipboard helpers."""

from __future__ import annotations

from urllib.parse import urlsplit

from blocks._common import error, ok
from domain.media.processor import write_clipboard

_MAX_CLIPBOARD_CHARS = 1_000_000
_LOCAL_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _header(headers, name):
    wanted = name.lower()
    for key, value in (headers or {}).items():
        if str(key).lower() == wanted:
            return str(value)
    return ""


def _origin_is_allowed(origin):
    if not origin:
        return True
    try:
        parsed = urlsplit(origin)
    except Exception:
        return False
    return parsed.hostname in _LOCAL_ORIGIN_HOSTS


def run(input_data, context):
    """Write text to the local clipboard from the first-party UI."""
    headers = input_data.get("_headers") if isinstance(input_data.get("_headers"), dict) else {}
    origin = _header(headers, "Origin")
    if not _origin_is_allowed(origin):
        response = error("origin not allowed for clipboard writes", "ORIGIN_DENIED")
        response["_http_status"] = 403
        return response

    content = input_data.get("content")
    if content is None:
        return error("content is required", "INVALID_INPUT")
    text = str(content)
    if len(text) > _MAX_CLIPBOARD_CHARS:
        return error("content is too large for clipboard", "CLIPBOARD_TOO_LARGE")

    try:
        write_clipboard(text)
    except Exception as exc:
        return error(str(exc), "CLIPBOARD_WRITE_ERROR")
    return ok({"written": True})
