from __future__ import annotations

import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List

from .oauth_store import provider_has_oauth_connection, provider_oauth_status


PROVIDER_SECRET_KEYS: Dict[str, List[str]] = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "cerebras": ["CEREBRAS_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "glm": ["GLM_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "llama_cpp": ["LLAMACPP_API_KEY"],
    "lmstudio": ["LMSTUDIO_API_KEY"],
    "longcat": ["LONGCAT_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "moonshotai": ["MOONSHOT_API_KEY"],
    "nvidia": ["NVIDIA_API_KEY", "NGC_API_KEY"],
    "ollama": ["OLLAMA_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "openai_compatible": ["OPENAI_COMPATIBLE_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "vllm": ["VLLM_API_KEY"],
    "xai": ["XAI_API_KEY"],
}

_NAMED_API_PREFIX = "RUMIAPI"
_SLUG_PATTERN = re.compile(r"[^A-Za-z0-9_]+")


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _secrets_dir(pack_root: Path | None = None) -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_SECRETS_DIR", "").strip()
    if override:
        return Path(override)
    return (pack_root or _pack_root()) / "user_data" / "secrets"


def _metadata_path(pack_root: Path | None = None) -> Path:
    return _secrets_dir(pack_root) / "provider_api_keys.json"


def _read_api_metadata(pack_root: Path | None = None) -> dict[str, dict[str, Any]]:
    path = _metadata_path(pack_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def _write_api_metadata(data: dict[str, dict[str, Any]], pack_root: Path | None = None) -> None:
    path = _metadata_path(pack_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _metadata_patch(
    *,
    provider_id: str,
    api_id: str,
    name: str,
    existing: dict[str, Any] | None = None,
    base_url: str | None = None,
    allowed_models: Any = None,
    default_model: str | None = None,
    notes: str | None = None,
    quota_label: str | None = None,
) -> dict[str, Any]:
    metadata = dict(existing or {})
    metadata.update(
        {
            "provider_id": str(provider_id or "").strip(),
            "api_id": str(api_id or "").strip(),
            "name": str(name or api_id or provider_id).strip(),
        }
    )
    optional_strings = {
        "base_url": base_url,
        "default_model": default_model,
        "notes": notes,
        "quota_label": quota_label,
    }
    for key, value in optional_strings.items():
        if value is None:
            continue
        cleaned = str(value or "").strip()
        if cleaned:
            metadata[key] = cleaned
        else:
            metadata.pop(key, None)

    if allowed_models is not None:
        models = _normalize_allowed_models(allowed_models)
        if models:
            metadata["allowed_models"] = models
        else:
            metadata.pop("allowed_models", None)
    return metadata


def _normalize_allowed_models(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.replace(",", "\n").splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        return []
    normalized: list[str] = []
    for item in raw_items:
        model_id = str(item or "").strip()
        if model_id and model_id not in normalized:
            normalized.append(model_id)
    return normalized


def _get_store(pack_root: Path | None = None):
    from core_runtime.secrets_store import SecretsStore

    return SecretsStore(str(_secrets_dir(pack_root)))


def _reset_ai_client() -> None:
    try:
        from domain.ai_client.client import AIClient

        AIClient._instance = None
    except Exception:
        pass


def _slug(value: str, *, fallback: str = "DEFAULT", max_length: int = 32) -> str:
    normalized = _SLUG_PATTERN.sub("_", str(value or "").strip()).strip("_").upper()
    normalized = re.sub(r"_+", "_", normalized)
    if not normalized:
        normalized = fallback
    return normalized[:max_length]


def named_provider_secret_key(provider_id: str, api_id: str | None = None, name: str | None = None) -> str:
    provider_slug = _slug(provider_id, fallback="PROVIDER", max_length=18)
    api_slug = _slug(api_id or name or "DEFAULT", fallback="DEFAULT", max_length=36)
    key = f"{_NAMED_API_PREFIX}_{provider_slug}_{api_slug}"
    return key[:64]


def _provider_from_named_key(key: str) -> str:
    prefix = f"{_NAMED_API_PREFIX}_"
    if not key.startswith(prefix):
        return ""
    remainder = key[len(prefix):]
    provider_slug = remainder.split("_", 1)[0].lower()
    provider_map = {_slug(provider_id, max_length=18).lower(): provider_id for provider_id in PROVIDER_SECRET_KEYS}
    return provider_map.get(provider_slug, provider_slug)


def _api_id_from_named_key(key: str, provider_id: str) -> str:
    provider_slug = _slug(provider_id, fallback="PROVIDER", max_length=18)
    prefix = f"{_NAMED_API_PREFIX}_{provider_slug}_"
    if key.startswith(prefix):
        return key[len(prefix):].lower()
    return key.lower()


def provider_secret_key(provider_id: str) -> str:
    keys = PROVIDER_SECRET_KEYS.get(str(provider_id or "").strip(), [])
    return keys[0] if keys else ""


def provider_secret_keys(provider_id: str) -> List[str]:
    return list(PROVIDER_SECRET_KEYS.get(str(provider_id or "").strip(), []))


def _read_secret_value(key: str, caller_id: str, *, pack_root: Path | None = None) -> str:
    value = os.environ.get(key, "").strip()
    if value:
        return value
    return str(
        _get_store(pack_root)._internal_read_value(
            key,
            caller_id=caller_id,
        )
        or ""
    ).strip()


def _refresh_provider_env(provider_id: str, *, pack_root: Path | None = None) -> bool:
    provider_id = str(provider_id or "").strip()
    keys = provider_secret_keys(provider_id)
    for key in keys:
        os.environ.pop(key, None)

    configured = False
    for key in keys:
        value = _read_secret_value(key, f"defaultspack.ai_client:{provider_id}:legacy", pack_root=pack_root)
        if value:
            os.environ[key] = value
            configured = True

    if not configured:
        canonical_key = provider_secret_key(provider_id)
        for api_key in provider_named_api_keys(provider_id, pack_root=pack_root):
            value = _read_secret_value(
                str(api_key.get("key", "")),
                f"defaultspack.ai_client:{provider_id}:{api_key.get('api_id')}",
                pack_root=pack_root,
            )
            if value and canonical_key:
                os.environ[canonical_key] = value
                configured = True
                break
    _reset_ai_client()
    return configured


def provider_has_api_key(provider_id: str, *, pack_root: Path | None = None) -> bool:
    keys = provider_secret_keys(provider_id)
    for key in keys:
        if os.environ.get(key, "").strip():
            return True
        secret_path = _secrets_dir(pack_root) / f"{key}.json"
        if secret_path.exists() and _get_store(pack_root).has_secret(key):
            return True
    provider_id = str(provider_id or "").strip()
    for item in provider_named_api_keys(provider_id, pack_root=pack_root):
        if item.get("configured"):
            return True
    return False


def set_provider_api_key(
    provider_id: str,
    value: str,
    *,
    pack_root: Path | None = None,
    api_id: str | None = None,
    name: str | None = None,
    base_url: str | None = None,
    allowed_models: Any = None,
    default_model: str | None = None,
    notes: str | None = None,
    quota_label: str | None = None,
) -> dict[str, Any]:
    named = bool(api_id or name)
    key = named_provider_secret_key(provider_id, api_id=api_id, name=name) if named else provider_secret_key(provider_id)
    if not key:
        return {"success": False, "provider_id": provider_id, "error": "unsupported provider"}
    normalized_api_id = str(api_id or _api_id_from_named_key(key, provider_id)).strip()
    display_name = str(name or normalized_api_id or provider_id).strip()

    cleaned = str(value or "").strip()
    if not cleaned:
        result = _get_store(pack_root).delete_secret(
            key,
            actor="defaultspack",
            reason=f"clear {provider_id} api key",
        )
        os.environ.pop(key, None)
        if result.success:
            if named:
                metadata = _read_api_metadata(pack_root)
                metadata.pop(key, None)
                _write_api_metadata(metadata, pack_root)
                _refresh_provider_env(provider_id, pack_root=pack_root)
            _reset_ai_client()
        return {
            "success": bool(result.success),
            "provider_id": provider_id,
            "api_id": normalized_api_id,
            "name": display_name,
            "key": key,
            "configured": False,
            "cleared": True,
            "error": result.error,
        }

    result = _get_store(pack_root).set_secret(
        key,
        cleaned,
        actor="defaultspack",
        reason=f"set {provider_id} api key",
    )
    if result.success:
        if named:
            metadata = _read_api_metadata(pack_root)
            metadata[key] = _metadata_patch(
                provider_id=provider_id,
                api_id=normalized_api_id,
                name=display_name,
                existing=metadata.get(key, {}),
                base_url=base_url,
                allowed_models=allowed_models,
                default_model=default_model,
                notes=notes,
                quota_label=quota_label,
            )
            _write_api_metadata(metadata, pack_root)
        if not named:
            os.environ[key] = cleaned
        elif not os.environ.get(provider_secret_key(provider_id), "").strip():
            canonical_key = provider_secret_key(provider_id)
            if canonical_key:
                os.environ[canonical_key] = cleaned
        _reset_ai_client()
    return {
        "success": bool(result.success),
        "provider_id": provider_id,
        "api_id": normalized_api_id,
        "name": display_name,
        "key": key,
        "configured": bool(result.success),
        "created": bool(result.created),
        "base_url": str(base_url or "").strip(),
        "allowed_models": _normalize_allowed_models(allowed_models),
        "default_model": str(default_model or "").strip(),
        "notes": str(notes or "").strip(),
        "quota_label": str(quota_label or "").strip(),
        "error": result.error,
    }


def delete_provider_api_key(
    provider_id: str,
    api_id: str,
    *,
    pack_root: Path | None = None,
) -> dict[str, Any]:
    api_id = str(api_id or "").strip()
    if not api_id:
        return {"success": False, "provider_id": provider_id, "error": "api_id is required"}
    return set_provider_api_key(provider_id, "", pack_root=pack_root, api_id=api_id)


def rename_provider_api_key(
    provider_id: str,
    api_id: str,
    name: str,
    *,
    pack_root: Path | None = None,
    new_api_id: str | None = None,
    base_url: str | None = None,
    allowed_models: Any = None,
    default_model: str | None = None,
    notes: str | None = None,
    quota_label: str | None = None,
) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    api_id = str(api_id or "").strip()
    display_name = str(name or new_api_id or api_id).strip()
    target_api_id = str(new_api_id or name or api_id).strip()
    if not provider_id or not api_id or not target_api_id:
        return {"success": False, "provider_id": provider_id, "api_id": api_id, "error": "provider_id and api_id are required"}

    old_key = named_provider_secret_key(provider_id, api_id=api_id)
    new_key = named_provider_secret_key(provider_id, api_id=target_api_id)
    metadata = _read_api_metadata(pack_root)
    if old_key == new_key:
        metadata[old_key] = _metadata_patch(
            provider_id=provider_id,
            api_id=api_id,
            name=display_name,
            existing=metadata.get(old_key, {}),
            base_url=base_url,
            allowed_models=allowed_models,
            default_model=default_model,
            notes=notes,
            quota_label=quota_label,
        )
        _write_api_metadata(metadata, pack_root)
        return {
            "success": True,
            "provider_id": provider_id,
            "api_id": api_id,
            "name": display_name,
            "key": old_key,
            "configured": True,
            "renamed": True,
        }

    if _get_store(pack_root).has_secret(new_key):
        return {"success": False, "provider_id": provider_id, "api_id": api_id, "error": "target api name already exists"}

    value = _read_secret_value(
        old_key,
        f"defaultspack.ai_client:{provider_id}:{api_id}:rename",
        pack_root=pack_root,
    )
    if not value:
        return {"success": False, "provider_id": provider_id, "api_id": api_id, "error": "api key not found"}

    saved = set_provider_api_key(
        provider_id,
        value,
        pack_root=pack_root,
        api_id=target_api_id,
        name=display_name,
        base_url=base_url,
        allowed_models=allowed_models,
        default_model=default_model,
        notes=notes,
        quota_label=quota_label,
    )
    if not saved.get("success"):
        return saved

    deleted = _get_store(pack_root).delete_secret(
        old_key,
        actor="defaultspack",
        reason=f"rename {provider_id} api key",
    )
    if deleted.success:
        os.environ.pop(old_key, None)
        metadata = _read_api_metadata(pack_root)
        metadata.pop(old_key, None)
        metadata[new_key] = _metadata_patch(
            provider_id=provider_id,
            api_id=str(saved.get("api_id") or target_api_id),
            name=display_name,
            existing=metadata.get(new_key, {}),
            base_url=base_url,
            allowed_models=allowed_models,
            default_model=default_model,
            notes=notes,
            quota_label=quota_label,
        )
        _write_api_metadata(metadata, pack_root)
        _refresh_provider_env(provider_id, pack_root=pack_root)
    return {
        "success": bool(deleted.success),
        "provider_id": provider_id,
        "api_id": str(saved.get("api_id") or target_api_id),
        "name": display_name,
        "key": new_key,
        "configured": bool(deleted.success),
        "renamed": bool(deleted.success),
        "error": deleted.error,
    }


def load_provider_api_keys_into_env(*, pack_root: Path | None = None) -> dict[str, bool]:
    loaded: dict[str, bool] = {}
    for provider_id, keys in PROVIDER_SECRET_KEYS.items():
        configured = False
        for key in keys:
            if os.environ.get(key, "").strip():
                configured = True
                continue
            if not (_secrets_dir(pack_root) / f"{key}.json").exists():
                continue
            store = _get_store(pack_root)
            value = store._internal_read_value(
                key,
                caller_id=f"defaultspack.ai_client:{provider_id}",
            )
            if value:
                os.environ[key] = value
                configured = True
        if not configured:
            canonical_key = provider_secret_key(provider_id)
            for api_key in provider_named_api_keys(provider_id, pack_root=pack_root):
                value = _get_store(pack_root)._internal_read_value(
                    str(api_key.get("key", "")),
                    caller_id=f"defaultspack.ai_client:{provider_id}:{api_key.get('api_id')}",
                )
                if value and canonical_key:
                    os.environ[canonical_key] = value
                    configured = True
                    break
        loaded[provider_id] = configured
    return loaded


def provider_named_api_keys(provider_id: str = "", *, pack_root: Path | None = None) -> list[dict[str, Any]]:
    requested_provider = str(provider_id or "").strip()
    if not _secrets_dir(pack_root).exists():
        return []
    store = _get_store(pack_root)
    metadata = _read_api_metadata(pack_root)
    items: list[dict[str, Any]] = []
    for meta in store.list_keys():
        key = str(meta.key or "")
        if not key.startswith(f"{_NAMED_API_PREFIX}_") or meta.deleted:
            continue
        key_provider = _provider_from_named_key(key)
        if requested_provider and key_provider != requested_provider:
            continue
        api_id = _api_id_from_named_key(key, key_provider)
        stored_meta = metadata.get(key, {})
        display_name = str(stored_meta.get("name") or api_id.replace("_", " ").title())
        item = {
            "api_id": api_id,
            "name": display_name,
            "provider_id": key_provider,
            "key": key,
            "label": f"{key_provider}:{api_id}:***",
            "configured": bool(meta.exists),
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
            "base_url": str(stored_meta.get("base_url") or ""),
            "allowed_models": _normalize_allowed_models(stored_meta.get("allowed_models", [])),
            "default_model": str(stored_meta.get("default_model") or ""),
            "notes": str(stored_meta.get("notes") or ""),
            "quota_label": str(stored_meta.get("quota_label") or ""),
        }
        items.append(item)
    return sorted(items, key=lambda item: (str(item.get("provider_id")), str(item.get("api_id"))))


def provider_api_metadata(provider_id: str, api_id: str, *, pack_root: Path | None = None) -> dict[str, Any]:
    provider_id = str(provider_id or "").strip()
    api_id = str(api_id or "").strip()
    if not provider_id or not api_id:
        return {}
    key = named_provider_secret_key(provider_id, api_id=api_id)
    metadata = _read_api_metadata(pack_root).get(key, {})
    if not isinstance(metadata, dict):
        return {}
    result = dict(metadata)
    result["allowed_models"] = _normalize_allowed_models(result.get("allowed_models", []))
    return result


def read_provider_api_key(provider_id: str, api_id: str, *, pack_root: Path | None = None) -> str | None:
    key = named_provider_secret_key(provider_id, api_id=api_id)
    value = _get_store(pack_root)._internal_read_value(
        key,
        caller_id=f"defaultspack.ai_client:{provider_id}:{api_id}",
    )
    if value:
        return value
    for legacy_key in provider_secret_keys(provider_id):
        value = os.environ.get(legacy_key, "").strip()
        if value:
            return value
        value = _get_store(pack_root)._internal_read_value(
            legacy_key,
            caller_id=f"defaultspack.ai_client:{provider_id}:legacy",
        )
        if value:
            return value
    return None


def provider_key_status(*, pack_root: Path | None = None) -> list[dict[str, Any]]:
    return [
        {
            "provider_id": provider_id,
            "key": keys[0],
            "keys": list(keys),
            "configured": (
                provider_has_api_key(provider_id, pack_root=pack_root)
                or provider_has_oauth_connection(provider_id, pack_root=pack_root)
            ),
            "apis": provider_named_api_keys(provider_id, pack_root=pack_root),
            "oauth": provider_oauth_status(provider_id, pack_root=pack_root),
        }
        for provider_id, keys in sorted(PROVIDER_SECRET_KEYS.items())
        if keys
    ]
