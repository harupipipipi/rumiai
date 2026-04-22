from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .categories import DEFAULT_CATEGORY_SPECS

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-/]{1,256}$")


class ManifestValidationError(ValueError):
    pass


def _as_dict(value: Any, key_name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    raise ManifestValidationError(f"{key_name} must be an object")


def validate_manifest(
    raw: Dict[str, Any],
    *,
    expected_category: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManifestValidationError("manifest root must be an object")

    manifest = dict(raw)
    ext_id = str(manifest.get("id", "")).strip()
    if not ext_id:
        raise ManifestValidationError("manifest.id is required")
    if not _ID_PATTERN.match(ext_id):
        raise ManifestValidationError(
            "manifest.id must match ^[A-Za-z0-9_.\\-/]{1,256}$"
        )

    category = str(manifest.get("category", "")).strip()
    if not category:
        raise ManifestValidationError("manifest.category is required")
    if category not in DEFAULT_CATEGORY_SPECS:
        raise ManifestValidationError(f"unsupported manifest.category: {category}")
    if expected_category and category != expected_category:
        raise ManifestValidationError(
            f"manifest.category mismatch: expected={expected_category}, actual={category}"
        )

    version = str(manifest.get("version", "1")).strip() or "1"
    enabled = bool(manifest.get("enabled", True))

    normalized: Dict[str, Any] = dict(manifest)
    normalized["id"] = ext_id
    normalized["category"] = category
    normalized["version"] = version
    normalized["enabled"] = enabled
    normalized["display_name"] = str(manifest.get("display_name", ext_id))
    normalized["description"] = str(manifest.get("description", ""))
    normalized["metadata"] = _as_dict(manifest.get("metadata"), "manifest.metadata")
    normalized["config"] = _as_dict(manifest.get("config"), "manifest.config")
    normalized["capabilities"] = _as_dict(
        manifest.get("capabilities"), "manifest.capabilities"
    )

    if category == "llm_provider":
        adapter = str(manifest.get("adapter", "")).strip()
        entrypoint = str(manifest.get("entrypoint", "")).strip()
        if not adapter and not entrypoint:
            raise ManifestValidationError(
                "llm_provider manifest requires either adapter or entrypoint"
            )
        if adapter:
            normalized["adapter"] = adapter
        if entrypoint:
            normalized["entrypoint"] = entrypoint
        api_key_env = str(manifest.get("api_key_env", "")).strip()
        if api_key_env:
            normalized["api_key_env"] = api_key_env
        base_url_env = str(manifest.get("base_url_env", "")).strip()
        if base_url_env:
            normalized["base_url_env"] = base_url_env
        default_base_url = str(manifest.get("default_base_url", "")).strip()
        if default_base_url:
            normalized["default_base_url"] = default_base_url
        default_model = str(manifest.get("default_model", "")).strip()
        if default_model:
            normalized["default_model"] = default_model
        default_model_for = _as_dict(
            manifest.get("default_model_for"), "manifest.default_model_for"
        )
        if default_model_for:
            normalized["default_model_for"] = {
                str(key): str(value) for key, value in default_model_for.items() if value
            }
        headers = _as_dict(manifest.get("headers"), "manifest.headers")
        if headers:
            normalized["headers"] = {
                str(key): str(value) for key, value in headers.items()
            }
        known_models = manifest.get("models")
        if known_models is not None:
            if not isinstance(known_models, list):
                raise ManifestValidationError("manifest.models must be an array")
            normalized["models"] = list(known_models)
        normalized["credential_required"] = bool(
            manifest.get("credential_required", bool(api_key_env))
        )
        normalized["priority"] = int(manifest.get("priority", 100))

    if category == "llm_model":
        provider_id = str(manifest.get("provider_id", "")).strip()
        model_id = str(manifest.get("model_id", "")).strip()
        if not provider_id or not model_id:
            if "/" in ext_id and not provider_id and not model_id:
                provider_id, model_id = ext_id.split("/", 1)
            else:
                raise ManifestValidationError(
                    "llm_model manifest requires provider_id and model_id"
                )
        normalized["provider_id"] = provider_id
        normalized["model_id"] = model_id
        normalized["display_name"] = str(
            manifest.get("display_name", model_id or ext_id)
        )
        normalized["defaults"] = _as_dict(manifest.get("defaults"), "manifest.defaults")
        normalized["priority"] = int(manifest.get("priority", 100))
        normalized["type"] = str(manifest.get("type", "chat"))

    return normalized
