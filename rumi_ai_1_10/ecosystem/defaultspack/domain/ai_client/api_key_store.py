from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List


PROVIDER_SECRET_KEYS: Dict[str, List[str]] = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "fireworks": ["FIREWORKS_API_KEY"],
    "genspark": ["GENSPARK_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "llama_cpp": ["LLAMACPP_API_KEY"],
    "llamacpp": ["LLAMACPP_API_KEY"],
    "longcat": ["LONGCAT_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "ollama": ["OLLAMA_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "openai_compatible": ["OPENAI_COMPATIBLE_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "vllm": ["VLLM_API_KEY"],
    "xai": ["XAI_API_KEY"],
}


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _secrets_dir(pack_root: Path | None = None) -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_SECRETS_DIR", "").strip()
    if override:
        return Path(override)
    return (pack_root or _pack_root()) / "user_data" / "secrets"


def _get_store(pack_root: Path | None = None):
    from core_runtime.secrets_store import SecretsStore

    return SecretsStore(str(_secrets_dir(pack_root)))


def _reset_ai_client() -> None:
    try:
        from domain.ai_client.client import AIClient

        AIClient._instance = None
    except Exception:
        pass


def provider_secret_key(provider_id: str) -> str:
    keys = PROVIDER_SECRET_KEYS.get(str(provider_id or "").strip(), [])
    return keys[0] if keys else ""


def provider_secret_keys(provider_id: str) -> List[str]:
    return list(PROVIDER_SECRET_KEYS.get(str(provider_id or "").strip(), []))


def provider_has_api_key(provider_id: str, *, pack_root: Path | None = None) -> bool:
    try:
        from domain.ai_client.key_resolver import KeyResolver

        resolved = KeyResolver(pack_root=pack_root).resolve_api_key(
            provider_id=provider_id,
            record_usage=False,
        )
        if resolved.get("configured"):
            return True
    except Exception:
        pass
    keys = provider_secret_keys(provider_id)
    if not keys:
        return False
    for key in keys:
        if os.environ.get(key, "").strip():
            return True
        secret_path = _secrets_dir(pack_root) / f"{key}.json"
        if secret_path.exists() and _get_store(pack_root).has_secret(key):
            return True
    return False


def set_provider_api_key(
    provider_id: str,
    value: str,
    *,
    pack_root: Path | None = None,
) -> dict[str, Any]:
    key = provider_secret_key(provider_id)
    if not key:
        return {"success": False, "provider_id": provider_id, "error": "unsupported provider"}

    cleaned = str(value or "").strip()
    if not cleaned:
        result = _get_store(pack_root).delete_secret(
            key,
            actor="defaultspack",
            reason=f"clear {provider_id} api key",
        )
        os.environ.pop(key, None)
        try:
            from domain.ai_client.key_manager import KeyManager

            KeyManager(pack_root=pack_root).delete_key(
                "legacy_{}_default".format(str(provider_id or "").strip())
            )
        except Exception:
            pass
        if result.success:
            _reset_ai_client()
        return {
            "success": bool(result.success),
            "provider_id": provider_id,
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
        os.environ[key] = cleaned
        try:
            from domain.ai_client.key_manager import KeyManager

            KeyManager(pack_root=pack_root).create_key(
                key_id="legacy_{}_default".format(str(provider_id or "").strip()),
                provider_id=str(provider_id or "").strip(),
                value=cleaned,
                name="{} default".format(str(provider_id or "").strip() or "provider"),
                env_var=key,
                default_for_provider=True,
                metadata={"legacy_secret_key": key},
            )
        except Exception:
            pass
        _reset_ai_client()
    return {
        "success": bool(result.success),
        "provider_id": provider_id,
        "key": key,
        "configured": bool(result.success),
        "created": bool(result.created),
        "error": result.error,
    }


def load_provider_api_keys_into_env(*, pack_root: Path | None = None) -> dict[str, bool]:
    loaded: dict[str, bool] = {}
    for provider_id, keys in PROVIDER_SECRET_KEYS.items():
        configured = False
        primary_key = keys[0] if keys else ""
        for key in keys:
            if os.environ.get(key, "").strip():
                configured = True
                continue
        if configured:
            loaded[provider_id] = True
            continue

        value = ""
        env_key = primary_key
        try:
            from domain.ai_client.key_resolver import KeyResolver

            resolved = KeyResolver(pack_root=pack_root).resolve_api_key(
                provider_id=provider_id,
                record_usage=False,
            )
            if resolved.get("configured"):
                value = str(resolved.get("value") or "")
                env_key = str(resolved.get("env_key") or primary_key)
        except Exception:
            value = ""

        if value and env_key:
            os.environ[env_key] = value
            configured = True
        else:
            for key in keys:
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
                    break
        loaded[provider_id] = configured
    return loaded


def provider_key_status(*, pack_root: Path | None = None) -> list[dict[str, Any]]:
    try:
        from domain.ai_client.key_manager import KeyManager

        named_keys = KeyManager(pack_root=pack_root).list_keys()
    except Exception:
        named_keys = []
    return [
        {
            "provider_id": provider_id,
            "key": keys[0],
            "keys": list(keys),
            "configured": provider_has_api_key(provider_id, pack_root=pack_root),
            "named_key_count": sum(
                1
                for item in named_keys
                if str(item.get("provider_id") or "") == provider_id
            ),
        }
        for provider_id, keys in sorted(PROVIDER_SECRET_KEYS.items())
        if keys
    ]
