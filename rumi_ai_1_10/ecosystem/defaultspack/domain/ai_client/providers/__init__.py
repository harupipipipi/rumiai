import os
from typing import Any, Dict, List

from ...extensions.loading import import_entrypoint
from ...extensions.runtime import get_extension_registry
from .openai_compatible_provider import OpenAICompatibleProvider

# Legacy fallback (extensions 未配置時の互換維持)
_LEGACY_PROVIDER_REGISTRY = [
    ("OPENAI_API_KEY", "openai", "ecosystem.defaultspack.domain.ai_client.providers.openai_provider", "OpenAIProvider"),
    ("ANTHROPIC_API_KEY", "anthropic", "ecosystem.defaultspack.domain.ai_client.providers.anthropic_provider", "AnthropicProvider"),
    ("GOOGLE_API_KEY", "google", "ecosystem.defaultspack.domain.ai_client.providers.google_provider", "GoogleProvider"),
    ("GENSPARK_API_KEY", "genspark", "ecosystem.defaultspack.domain.ai_client.providers.genspark_provider", "GensparkProvider"),
]


def _load_provider_manifests() -> List[Dict[str, Any]]:
    try:
        registry = get_extension_registry(force_reload=True)
        return registry.llm().providers(enabled_only=True)
    except Exception:
        return []


def _load_model_manifests(provider_id: str = "") -> List[Dict[str, Any]]:
    try:
        registry = get_extension_registry(force_reload=True)
        return registry.llm().models(provider_id=provider_id, enabled_only=True)
    except Exception:
        return []


def _credentials_ready(manifest: Dict[str, Any]) -> bool:
    if not bool(manifest.get("credential_required", False)):
        return True
    api_key_env = str(manifest.get("api_key_env", "")).strip()
    if not api_key_env:
        return True
    return bool(os.environ.get(api_key_env))


def _instantiate_manifest_provider(manifest: Dict[str, Any]):
    adapter = str(manifest.get("adapter", "")).strip()
    if adapter == "openai_compatible":
        return OpenAICompatibleProvider.from_manifest(
            manifest,
            model_manifests=_load_model_manifests(str(manifest.get("id", "")).strip()),
        )

    entrypoint = str(manifest.get("entrypoint", "")).strip()
    if not entrypoint:
        return None
    provider_cls = import_entrypoint(entrypoint)
    return provider_cls()


def _load_legacy_providers() -> Dict[str, Any]:
    available = {}
    for env_var, name, module_path, class_name in _LEGACY_PROVIDER_REGISTRY:
        if not os.environ.get(env_var, ""):
            continue
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            available[name] = cls()
        except Exception:
            continue
    return available


def detect_available_providers():
    """manifest 駆動で利用可能 provider を検出し、必要時は legacy へフォールバックする。"""
    available = {}
    manifests = _load_provider_manifests()
    for manifest in manifests:
        provider_id = str(manifest.get("id", "")).strip()
        if not provider_id:
            continue
        if not _credentials_ready(manifest):
            continue
        try:
            provider = _instantiate_manifest_provider(manifest)
        except Exception:
            provider = None
        if provider is not None:
            available[provider_id] = provider

    if not available:
        available.update(_load_legacy_providers())
    return available


def detect_rumi_provider(client):
    """rumi provider を必要時に生成する。"""
    non_stub = [name for name in client._providers if name != "stub"]
    if not non_stub:
        return None
    manifests = _load_provider_manifests()
    for manifest in manifests:
        if manifest.get("id") == "rumi" and not bool(manifest.get("enabled", True)):
            return None
    try:
        from .rumi_provider import RumiProvider
        return RumiProvider(client)
    except Exception:
        return None


def get_best_model_for_provider(name, use_case="chat"):
    """manifest 優先で provider の推奨モデル ID を返す。"""
    try:
        registry = get_extension_registry(force_reload=True)
        best = registry.llm().best_model(name, use_case=use_case)
        if best is not None:
            return str(best.get("model_id", ""))
        provider_manifest = registry.get("llm_provider", name)
        if provider_manifest:
            defaults = provider_manifest.get("default_model_for", {}) or {}
            if use_case in defaults:
                return str(defaults[use_case])
            if provider_manifest.get("default_model"):
                return str(provider_manifest["default_model"])
    except Exception:
        pass

    if name == "stub":
        return "default"
    return None


def get_all_known_models():
    """manifest と provider の両方から既知モデル一覧を返す。"""
    models = []
    seen_ids = set()

    for manifest in _load_model_manifests():
        provider_id = str(manifest.get("provider_id", "")).strip()
        model_id = str(manifest.get("model_id", "")).strip()
        if not provider_id or not model_id:
            continue
        full_id = f"{provider_id}/{model_id}"
        if full_id in seen_ids:
            continue
        seen_ids.add(full_id)
        models.append(
            {
                "id": full_id,
                "name": manifest.get("display_name", model_id),
                "provider": provider_id,
                "type": manifest.get("type", "chat"),
            }
        )

    providers = detect_available_providers()
    for provider in providers.values():
        known = getattr(provider, "KNOWN_MODELS", [])
        if callable(getattr(provider, "list_models", None)):
            try:
                listed = provider.list_models()
                if isinstance(listed, list) and listed:
                    known = listed
            except Exception:
                pass
        for model in known:
            if not isinstance(model, dict):
                continue
            mid = str(model.get("id", "")).strip()
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            models.append(dict(model))

    try:
        from .rumi_provider import RumiProvider

        for model in getattr(RumiProvider, "KNOWN_MODELS", []):
            if not isinstance(model, dict):
                continue
            mid = str(model.get("id", "")).strip()
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            models.append(dict(model))
    except Exception:
        pass

    return models
