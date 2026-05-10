from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_RESPONSE_CAPABILITIES: dict[str, dict[str, Any]] = {
    "discord": {
        "provider": "discord",
        "capabilities": {
            "text": {"enabled": True, "max_chars": 2000, "supports_markdown": True, "allowed_mentions_control": True},
            "files": {
                "enabled": True,
                "max_files_per_message": 10,
                "max_bytes_per_file": 8388608,
                "allowed_mime": ["image/png", "image/jpeg", "image/webp", "text/plain", "application/pdf"],
            },
            "embeds": {"enabled": True},
            "transforms": {"text_chunking": True, "file_to_link_fallback": True, "image_resize": False},
        },
    },
    "line": {
        "provider": "line",
        "capabilities": {
            "text": {"enabled": True, "max_chars": 5000, "supports_markdown": False},
            "files": {"enabled": False},
            "images": {"enabled": True, "max_bytes_per_image": 10485760, "allowed_mime": ["image/jpeg", "image/png"]},
            "reply": {"supports_reply_token": True, "supports_push": True},
        },
    },
    "generic": {
        "provider": "generic",
        "capabilities": {
            "text": {"enabled": True, "max_chars": 8000, "supports_markdown": True},
            "files": {"enabled": False},
            "transforms": {"text_chunking": True, "file_to_link_fallback": True},
        },
    },
}


def response_capabilities(provider: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = deepcopy(DEFAULT_RESPONSE_CAPABILITIES.get(str(provider or "").strip(), DEFAULT_RESPONSE_CAPABILITIES["generic"]))
    if isinstance(overrides, dict):
        base = _deep_merge(base, overrides)
    return base


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
