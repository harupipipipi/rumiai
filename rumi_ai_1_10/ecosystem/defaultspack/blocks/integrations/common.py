from __future__ import annotations

import base64
import os
from typing import Dict


def headers_from_request(input_data) -> Dict[str, str]:
    headers = input_data.get("_headers") if isinstance(input_data, dict) else {}
    if not isinstance(headers, dict):
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def raw_body_bytes(input_data) -> bytes:
    encoded = input_data.get("_raw_body_base64") if isinstance(input_data, dict) else ""
    if isinstance(encoded, str) and encoded:
        try:
            return base64.b64decode(encoded)
        except Exception:
            pass
    raw = input_data.get("_raw_body", "") if isinstance(input_data, dict) else ""
    return str(raw or "").encode("utf-8")


def text_limit(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def allow_unsigned_webhook_dev() -> bool:
    return os.environ.get("RUMI_DEFAULTSPACK_INTEGRATIONS_ALLOW_UNSIGNED_DEV", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
