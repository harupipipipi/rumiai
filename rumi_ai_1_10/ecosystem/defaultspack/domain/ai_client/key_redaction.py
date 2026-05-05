from __future__ import annotations

import re
from typing import Any


_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|credential|password|secret|token|value)",
    re.IGNORECASE,
)


def redact_secret(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    if not text:
        return ""
    if len(text) <= 8:
        return "[redacted]"
    return "{}...[redacted]...{}".format(text[:4], text[-4:])


def redact_mapping(value: Any, *, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SENSITIVE_KEY_RE.search(key_text):
                redacted[key] = redact_secret(item)
            else:
                redacted[key] = redact_mapping(item, parent_key=key_text)
        return redacted
    if isinstance(value, list):
        return [redact_mapping(item, parent_key=parent_key) for item in value]
    if parent_key and _SENSITIVE_KEY_RE.search(parent_key):
        return redact_secret(value)
    return value
