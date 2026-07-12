from __future__ import annotations

import re
from typing import Any


EXPLICIT_AUDIO_BOOL_KEYS = {
    "supports_audio",
    "supports_audio_input",
    "audio_input",
    "input_audio",
}
AUDIO_INPUT_TOKENS = {
    "audio",
    "audio_input",
    "input_audio",
    "speech",
    "speech_input",
    "speech_to_text",
    "transcription",
    "transcribe",
    "stt",
    "asr",
}

CAPABILITY_CONTAINERS = ("capabilities", "capability_map", "features")
TAG_CONTAINERS = ("capability_tags", "tags", "traits")
MODALITY_CONTAINERS = ("input_modalities", "modalities", "modalities_input")


def metadata_supports_audio_input(
    model: dict[str, Any] | None,
    *,
    _seen: set[int] | None = None,
    _depth: int = 0,
) -> bool:
    if not isinstance(model, dict) or _depth > 8:
        return False
    seen = _seen or set()
    marker = id(model)
    if marker in seen:
        return False
    explicit = explicit_audio_input_bool(model, _seen=set(seen), _depth=_depth)
    if explicit is True:
        return True
    seen.add(marker)
    if _truthy_named_field(model, AUDIO_INPUT_TOKENS):
        return True
    if _containers_include_audio(model, CAPABILITY_CONTAINERS):
        return True
    if _containers_include_audio(model, TAG_CONTAINERS):
        return True
    if _modalities_include_audio(model):
        return True

    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    if metadata_supports_audio_input(metadata, _seen=seen, _depth=_depth + 1):
        return True

    model_capabilities = model.get("model_capabilities")
    if (
        isinstance(model_capabilities, dict)
        and metadata_supports_audio_input(
            model_capabilities,
            _seen=seen,
            _depth=_depth + 1,
        )
    ):
        return True
    return False


def explicit_audio_input_bool(
    model: dict[str, Any] | None,
    *,
    _seen: set[int] | None = None,
    _depth: int = 0,
) -> bool | None:
    if not isinstance(model, dict) or _depth > 8:
        return None
    seen = _seen or set()
    marker = id(model)
    if marker in seen:
        return None
    seen.add(marker)
    for key, item in model.items():
        if _normalize_token(key) in EXPLICIT_AUDIO_BOOL_KEYS and item is not None:
            return bool(item)
    capabilities = model.get("capabilities")
    if isinstance(capabilities, dict):
        for key, item in capabilities.items():
            if _normalize_token(key) in EXPLICIT_AUDIO_BOOL_KEYS and item is not None:
                return bool(item)
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    if metadata:
        nested = explicit_audio_input_bool(
            metadata,
            _seen=seen,
            _depth=_depth + 1,
        )
        if nested is not None:
            return nested
    return None


def _truthy_named_field(value: dict[str, Any], tokens: set[str]) -> bool:
    for key, item in value.items():
        if _normalize_token(key) in tokens and bool(item):
            return True
    return False


def _containers_include_audio(value: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        if _token_value_includes_audio(value.get(key)):
            return True
    return False


def _modalities_include_audio(value: dict[str, Any]) -> bool:
    for key in MODALITY_CONTAINERS:
        raw = value.get(key)
        if isinstance(raw, dict):
            if _token_value_includes_audio(raw.get("input")):
                return True
            if _token_value_includes_audio(raw.get("inputs")):
                return True
            if _token_value_includes_audio(raw.get("input_modalities")):
                return True
        elif _token_value_includes_audio(raw):
            return True
    return False


def _token_value_includes_audio(
    value: Any,
    *,
    _seen: set[int] | None = None,
    _depth: int = 0,
) -> bool:
    if _depth > 8:
        return False
    if isinstance(value, dict):
        seen = _seen or set()
        marker = id(value)
        if marker in seen:
            return False
        seen.add(marker)
        return any(
            (_normalize_token(key) in AUDIO_INPUT_TOKENS and bool(item))
            or _token_value_includes_audio(item, _seen=seen, _depth=_depth + 1)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        seen = _seen or set()
        marker = id(value)
        if marker in seen:
            return False
        seen.add(marker)
        return any(
            _token_value_includes_audio(item, _seen=seen, _depth=_depth + 1)
            for item in value
        )
    if isinstance(value, str):
        return _normalize_token(value) in AUDIO_INPUT_TOKENS
    return False


def _normalize_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
