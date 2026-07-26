from __future__ import annotations

import re
import urllib.parse


_OPERATION_SUFFIXES = {
    "/chat/completions",
    "/responses",
    "/messages",
    "/models",
    "/embeddings",
    "/audio/speech",
    "/audio/transcriptions",
    "/images/generations",
}


def normalize_provider_base_url(value: str, *, allow_empty: bool = False) -> str:
    """Validate and normalize a provider API base URL.

    A base URL identifies an API root, not an individual operation.  Query
    strings, fragments, embedded credentials, and operation endpoints are
    rejected so callers cannot accidentally build ambiguous or unsafe URLs.
    """

    raw = str(value or "").strip()
    if not raw:
        if allow_empty:
            return ""
        raise ValueError("provider base URL is required")

    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("provider base URL must use http or https")
    if not parsed.hostname:
        raise ValueError("provider base URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("provider base URL must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("provider base URL must not include a query or fragment")

    path = re.sub(r"/{2,}", "/", parsed.path or "").rstrip("/")
    lowered_path = path.lower()
    if any(lowered_path.endswith(suffix) for suffix in _OPERATION_SUFFIXES):
        raise ValueError("provider base URL must identify an API root, not an operation endpoint")

    netloc = parsed.netloc.lower()
    return urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def provider_endpoint_url(base_url: str, path: str) -> str:
    base = normalize_provider_base_url(base_url)
    operation = "/" + str(path or "").lstrip("/")
    return base + operation
