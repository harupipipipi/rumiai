from __future__ import annotations

import importlib
import os
from typing import Any, Dict, Iterable, List, Optional

from ...extensions.loading import import_entrypoint
from ...extensions.runtime import get_extension_registry
from .openai_compatible_provider import OpenAICompatibleProvider

"""
providers package - provider discovery and catalog helpers.

The extension registry is the primary runtime source of truth. Curated metadata
below exists only to preserve the richer master-side catalog/API surface when a
manifest does not spell out every compatibility field.
"""


_LEGACY_PROVIDER_REGISTRY = [
    (
        "OPENAI_API_KEY",
        "openai",
        "ecosystem.defaultspack.domain.ai_client.providers.openai_provider",
        "OpenAIProvider",
    ),
    (
        "ANTHROPIC_API_KEY",
        "anthropic",
        "ecosystem.defaultspack.domain.ai_client.providers.anthropic_provider",
        "AnthropicProvider",
    ),
    (
        "GOOGLE_API_KEY",
        "google",
        "ecosystem.defaultspack.domain.ai_client.providers.google_provider",
        "GoogleProvider",
    ),
    (
        "GENSPARK_API_KEY",
        "genspark",
        "ecosystem.defaultspack.domain.ai_client.providers.genspark_provider",
        "GensparkProvider",
    ),
]

_CURATED_PROVIDER_METADATA: Dict[str, Dict[str, Any]] = {
    "stub": {
        "display_name": "Stub",
        "kind": "builtin",
        "description": "Built-in test provider for deterministic responses.",
        "env_vars": [],
        "base_url_envs": [],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "default",
        "capabilities": ["chat", "embedding", "image", "transcription", "tts"],
    },
    "openai": {
        "display_name": "OpenAI",
        "kind": "cloud",
        "description": "OpenAI hosted models and multimodal APIs.",
        "env_vars": ["OPENAI_API_KEY"],
        "base_url_envs": ["OPENAI_BASE_URL"],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "gpt-5.4",
        "capabilities": [
            "chat",
            "tool_calls",
            "vision",
            "embedding",
            "image",
            "transcription",
            "tts",
        ],
    },
    "anthropic": {
        "display_name": "Anthropic",
        "kind": "cloud",
        "description": "Anthropic Claude models.",
        "env_vars": ["ANTHROPIC_API_KEY"],
        "base_url_envs": ["ANTHROPIC_BASE_URL"],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "claude-sonnet-4-0",
        "capabilities": ["chat", "tool_calls", "vision", "reasoning"],
    },
    "google": {
        "display_name": "Google",
        "kind": "cloud",
        "description": "Google Gemini and multimodal APIs.",
        "env_vars": ["GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"],
        "base_url_envs": ["GOOGLE_BASE_URL"],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "gemini-2.5-pro",
        "capabilities": ["chat", "tool_calls", "vision", "embedding"],
    },
    "genspark": {
        "display_name": "Genspark",
        "kind": "cloud",
        "description": "Genspark OpenAI-compatible hosted models.",
        "env_vars": ["GENSPARK_API_KEY", "OPENAI_API_KEY"],
        "base_url_envs": ["GENSPARK_LLM_BASE_URL", "OPENAI_BASE_URL"],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "gpt-5-mini",
        "capabilities": ["chat", "tool_calls", "vision"],
    },
    "groq": {
        "display_name": "Groq",
        "kind": "cloud",
        "description": "Fast hosted inference for open-weight models.",
        "env_vars": ["GROQ_API_KEY"],
        "base_url_envs": ["GROQ_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "llama-3.3-70b-versatile",
        "capabilities": ["chat", "tool_calls"],
    },
    "mistral": {
        "display_name": "Mistral",
        "kind": "cloud",
        "description": "Mistral hosted models.",
        "env_vars": ["MISTRAL_API_KEY"],
        "base_url_envs": ["MISTRAL_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "mistral-large-latest",
        "capabilities": ["chat", "embedding"],
    },
    "xai": {
        "display_name": "xAI",
        "kind": "cloud",
        "description": "xAI Grok models.",
        "env_vars": ["XAI_API_KEY"],
        "base_url_envs": ["XAI_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "grok-2-latest",
        "capabilities": ["chat", "vision"],
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "kind": "aggregator",
        "description": "Aggregator for many provider-backed models.",
        "env_vars": ["OPENROUTER_API_KEY"],
        "base_url_envs": ["OPENROUTER_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "gpt-4o-mini",
        "capabilities": ["chat", "tool_calls", "vision"],
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "kind": "cloud",
        "description": "DeepSeek chat and reasoning models.",
        "env_vars": ["DEEPSEEK_API_KEY"],
        "base_url_envs": ["DEEPSEEK_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "deepseek-chat",
        "capabilities": ["chat", "reasoning"],
    },
    "perplexity": {
        "display_name": "Perplexity",
        "kind": "aggregator",
        "description": "Perplexity online and sonar models.",
        "env_vars": ["PERPLEXITY_API_KEY"],
        "base_url_envs": ["PERPLEXITY_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "sonar-pro",
        "capabilities": ["chat", "search"],
    },
    "together": {
        "display_name": "Together",
        "kind": "aggregator",
        "description": "Hosted inference for open models.",
        "env_vars": ["TOGETHER_API_KEY"],
        "base_url_envs": ["TOGETHER_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "llama-3.1-70b-instruct-turbo",
        "capabilities": ["chat", "tool_calls"],
    },
    "fireworks": {
        "display_name": "Fireworks",
        "kind": "aggregator",
        "description": "Hosted inference and image APIs for open models.",
        "env_vars": ["FIREWORKS_API_KEY"],
        "base_url_envs": ["FIREWORKS_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "accounts/fireworks/models/llama-v3p1-70b-instruct",
        "capabilities": ["chat", "tool_calls", "vision", "image", "embedding"],
    },
    "glm": {
        "display_name": "GLM",
        "kind": "cloud",
        "description": "GLM hosted models via an OpenAI-compatible surface.",
        "env_vars": ["GLM_API_KEY"],
        "base_url_envs": ["GLM_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "glm-4.5",
        "capabilities": ["chat", "tool_calls", "streaming"],
    },
    "longcat": {
        "display_name": "Longcat",
        "kind": "cloud",
        "description": "Longcat hosted models via an OpenAI-compatible surface.",
        "env_vars": ["LONGCAT_API_KEY"],
        "base_url_envs": ["LONGCAT_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "longcat-chat",
        "capabilities": ["chat", "streaming"],
    },
    "ollama": {
        "display_name": "Ollama",
        "kind": "local",
        "description": "Local models served by Ollama.",
        "env_vars": [],
        "base_url_envs": ["OLLAMA_BASE_URL", "OLLAMA_HOST"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "llama3.1:8b",
        "default_base_url": "http://127.0.0.1:11434/v1",
        "capabilities": ["chat", "embedding", "local", "openai_compatible"],
    },
    "lmstudio": {
        "display_name": "LM Studio",
        "kind": "local",
        "description": "Local OpenAI-compatible endpoint from LM Studio.",
        "env_vars": [],
        "base_url_envs": ["LMSTUDIO_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "deepseek-r1",
        "default_base_url": "http://127.0.0.1:1234/v1",
        "capabilities": ["chat", "embedding", "local", "openai_compatible"],
    },
    "vllm": {
        "display_name": "vLLM",
        "kind": "local",
        "description": "Self-hosted OpenAI-compatible inference server.",
        "env_vars": [],
        "base_url_envs": ["VLLM_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "deepseek-r1",
        "default_base_url": "http://127.0.0.1:8000/v1",
        "capabilities": ["chat", "embedding", "local", "openai_compatible"],
    },
    "llamacpp": {
        "display_name": "llama.cpp",
        "kind": "local",
        "description": "Local OpenAI-compatible inference server.",
        "env_vars": [],
        "base_url_envs": ["LLAMACPP_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "local-gguf",
        "default_base_url": "http://127.0.0.1:8080/v1",
        "capabilities": ["chat", "embedding", "local", "openai_compatible"],
    },
    "openai_compatible": {
        "display_name": "OpenAI Compatible",
        "kind": "custom",
        "description": "Generic OpenAI-compatible endpoint.",
        "env_vars": ["OPENAI_COMPATIBLE_API_KEY"],
        "base_url_envs": ["OPENAI_COMPATIBLE_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "custom-model",
        "capabilities": ["chat", "tool_calls", "embedding", "openai_compatible"],
    },
    "rumi": {
        "display_name": "Rumi",
        "kind": "meta",
        "description": "Meta-provider for routing and orchestration.",
        "env_vars": [],
        "base_url_envs": [],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "default",
        "capabilities": ["chat", "routing", "meta"],
    },
}

_CURATED_PROVIDER_MODELS: Dict[str, List[Dict[str, Any]]] = {
    "stub": [
        {"model_id": "default", "name": "Stub Default Model", "type": "chat"},
        {"model_id": "fast", "name": "Stub Fast Model", "type": "chat"},
        {"model_id": "large", "name": "Stub Large Model", "type": "chat"},
    ],
    "groq": [
        {"model_id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B Versatile", "type": "chat"},
        {"model_id": "qwen-qwq-32b", "name": "QWQ 32B", "type": "reasoning"},
        {
            "model_id": "deepseek-r1-distill-llama-70b",
            "name": "DeepSeek R1 Distill Llama 70B",
            "type": "reasoning",
        },
    ],
    "mistral": [
        {"model_id": "mistral-large-latest", "name": "Mistral Large", "type": "chat"},
        {"model_id": "ministral-8b-latest", "name": "Ministral 8B", "type": "chat"},
        {"model_id": "codestral-latest", "name": "Codestral", "type": "chat"},
    ],
    "xai": [
        {"model_id": "grok-2-latest", "name": "Grok 2", "type": "chat"},
        {"model_id": "grok-vision-beta", "name": "Grok Vision", "type": "vision"},
    ],
    "openrouter": [
        {"model_id": "gpt-4o-mini", "name": "GPT-4o Mini", "type": "chat"},
        {"model_id": "claude-sonnet-4", "name": "Claude Sonnet 4", "type": "chat"},
        {"model_id": "deepseek-r1", "name": "DeepSeek R1", "type": "reasoning"},
    ],
    "deepseek": [
        {"model_id": "deepseek-chat", "name": "DeepSeek Chat", "type": "chat"},
        {"model_id": "deepseek-r1", "name": "DeepSeek R1", "type": "reasoning"},
    ],
    "perplexity": [
        {"model_id": "sonar-pro", "name": "Sonar Pro", "type": "chat"},
        {"model_id": "sonar-reasoning-pro", "name": "Sonar Reasoning Pro", "type": "reasoning"},
    ],
    "together": [
        {"model_id": "llama-3.1-70b-instruct-turbo", "name": "Llama 3.1 70B Instruct Turbo", "type": "chat"},
        {"model_id": "qwen2.5-coder-32b-instruct", "name": "Qwen 2.5 Coder 32B Instruct", "type": "chat"},
        {"model_id": "deepseek-r1", "name": "DeepSeek R1", "type": "reasoning"},
    ],
    "fireworks": [
        {
            "model_id": "accounts/fireworks/models/llama-v3p1-70b-instruct",
            "name": "Llama 3.1 70B Instruct",
            "type": "chat",
        }
    ],
    "glm": [{"model_id": "glm-4.5", "name": "GLM 4.5", "type": "chat"}],
    "longcat": [{"model_id": "longcat-chat", "name": "Longcat Chat", "type": "chat"}],
    "ollama": [
        {"model_id": "llama3.1:8b", "name": "Llama 3.1 8B", "type": "chat"},
        {"model_id": "qwen2.5-coder:7b", "name": "Qwen 2.5 Coder 7B", "type": "chat"},
        {"model_id": "deepseek-r1", "name": "DeepSeek R1", "type": "reasoning"},
    ],
    "lmstudio": [
        {"model_id": "deepseek-r1", "name": "DeepSeek R1", "type": "reasoning"},
        {"model_id": "llama3.1:8b", "name": "Llama 3.1 8B", "type": "chat"},
        {"model_id": "gpt-oss-20b", "name": "GPT OSS 20B", "type": "chat"},
    ],
    "vllm": [
        {"model_id": "deepseek-r1", "name": "DeepSeek R1", "type": "reasoning"},
        {"model_id": "qwen2.5-coder:32b", "name": "Qwen 2.5 Coder 32B", "type": "chat"},
        {"model_id": "gpt-oss-20b", "name": "GPT OSS 20B", "type": "chat"},
    ],
    "llamacpp": [{"model_id": "local-gguf", "name": "Local GGUF Model", "type": "chat"}],
    "openai_compatible": [
        {"model_id": "custom-model", "name": "Custom Model", "type": "chat"},
    ],
}

_BEST_MODEL_BY_PROVIDER = {
    "stub": "default",
    "openai": "gpt-5.4",
    "anthropic": "claude-sonnet-4-0",
    "google": "gemini-2.5-pro",
    "genspark": "gpt-5-mini",
    "groq": "llama-3.3-70b-versatile",
    "mistral": "mistral-large-latest",
    "xai": "grok-2-latest",
    "openrouter": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "perplexity": "sonar-pro",
    "together": "llama-3.1-70b-instruct-turbo",
    "fireworks": "accounts/fireworks/models/llama-v3p1-70b-instruct",
    "glm": "glm-4.5",
    "longcat": "longcat-chat",
    "ollama": "llama3.1:8b",
    "lmstudio": "deepseek-r1",
    "vllm": "deepseek-r1",
    "llamacpp": "local-gguf",
    "openai_compatible": "custom-model",
    "rumi": "default",
}


def _list_provider_manifests() -> List[Dict[str, Any]]:
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


def _provider_manifest_map() -> Dict[str, Dict[str, Any]]:
    manifests: Dict[str, Dict[str, Any]] = {}
    for manifest in _list_provider_manifests():
        provider_id = str(manifest.get("id", "")).strip()
        if provider_id:
            manifests[provider_id] = dict(manifest)
    return manifests


def _truthy_env(env_name: str) -> bool:
    return bool(str(os.environ.get(env_name, "") or "").strip())


def _manifest_env_list(*values: Any) -> List[str]:
    envs: List[str] = []
    for value in values:
        if isinstance(value, str):
            item = value.strip()
            if item and item not in envs:
                envs.append(item)
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                item = str(nested or "").strip()
                if item and item not in envs:
                    envs.append(item)
    return envs


def _capability_list(manifest: Dict[str, Any], curated: Dict[str, Any]) -> List[str]:
    capabilities: List[str] = []

    def _add(value: str) -> None:
        item = str(value or "").strip()
        if item and item not in capabilities:
            capabilities.append(item)

    for item in curated.get("capabilities", []):
        _add(item)

    raw_caps = manifest.get("capabilities", {})
    if isinstance(raw_caps, dict):
        for key, enabled in raw_caps.items():
            if enabled:
                _add(key)
    elif isinstance(raw_caps, (list, tuple, set)):
        for item in raw_caps:
            _add(str(item))

    adapter = str(manifest.get("adapter", "")).strip()
    if adapter == "openai_compatible":
        _add("openai_compatible")
    return capabilities


def _infer_kind(provider_id: str, manifest: Dict[str, Any], curated: Dict[str, Any]) -> str:
    if curated.get("kind"):
        return str(curated["kind"])
    if provider_id == "stub":
        return "builtin"
    if provider_id == "rumi":
        return "meta"
    if provider_id in {"openrouter", "together", "fireworks", "perplexity"}:
        return "aggregator"
    if provider_id in {"ollama", "lmstudio", "vllm", "llamacpp", "openai_compatible"}:
        return "local"
    if str(manifest.get("adapter", "")).strip() == "openai_compatible":
        return "cloud"
    return "cloud"


def _provider_catalog_only(provider_id: str, manifest: Dict[str, Any], curated: Dict[str, Any]) -> bool:
    if "catalog_only" in curated:
        return bool(curated["catalog_only"])
    adapter = str(manifest.get("adapter", "")).strip()
    return adapter == "openai_compatible" and provider_id not in {"stub", "rumi"}


def _provider_supports_invoke(provider_id: str, manifest: Dict[str, Any], curated: Dict[str, Any]) -> bool:
    if "supports_invoke" in curated:
        return bool(curated["supports_invoke"])
    adapter = str(manifest.get("adapter", "")).strip()
    entrypoint = str(manifest.get("entrypoint", "")).strip()
    return bool(entrypoint or adapter == "python_entrypoint" or provider_id in {"stub", "rumi"})


def _merge_provider_entry(provider_id: str, manifest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    manifest = dict(manifest or {})
    curated = dict(_CURATED_PROVIDER_METADATA.get(provider_id, {}))
    display_name = str(
        manifest.get("display_name")
        or curated.get("display_name")
        or provider_id.replace("_", " ").title()
    )
    env_vars = _manifest_env_list(manifest.get("api_key_env"), curated.get("env_vars", []))
    base_url_envs = _manifest_env_list(manifest.get("base_url_env"), curated.get("base_url_envs", []))
    default_model = str(
        manifest.get("default_model")
        or (manifest.get("default_model_for", {}) or {}).get("chat")
        or curated.get("default_model")
        or ""
    )
    default_base_url = str(
        manifest.get("default_base_url")
        or curated.get("default_base_url")
        or ""
    ).strip()
    adapter = str(manifest.get("adapter", "")).strip()
    entrypoint = str(manifest.get("entrypoint", "")).strip()
    return {
        "id": provider_id,
        "provider_id": provider_id,
        "display_name": display_name,
        "name": display_name,
        "kind": _infer_kind(provider_id, manifest, curated),
        "description": str(manifest.get("description") or curated.get("description") or ""),
        "env_vars": env_vars,
        "base_url_envs": base_url_envs,
        "default_model": default_model,
        "default_base_url": default_base_url,
        "catalog_only": _provider_catalog_only(provider_id, manifest, curated),
        "supports_invoke_base": _provider_supports_invoke(provider_id, manifest, curated),
        "capabilities": _capability_list(manifest, curated),
        "credential_required": bool(manifest.get("credential_required", True)),
        "adapter": adapter,
        "entrypoint": entrypoint,
        "priority": int(manifest.get("priority", 100)),
        "manifest": manifest,
    }


def _provider_is_configured(entry: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    for env_name in entry.get("env_vars", []):
        if _truthy_env(env_name):
            return True, env_name
    for env_name in entry.get("base_url_envs", []):
        if _truthy_env(env_name):
            return True, env_name
    if entry.get("kind") == "local" and entry.get("default_base_url"):
        return True, "default_local_endpoint"
    if entry["provider_id"] == "stub":
        return True, "builtin"
    return False, None


def _provider_status(entry: Dict[str, Any], active: bool, configured: bool) -> str:
    if active:
        return "active"
    if entry.get("catalog_only"):
        return "catalog_only"
    if configured:
        return "configured"
    return "unconfigured"


def get_provider_catalog(active_provider_ids=None):
    active_ids = set(active_provider_ids or [])
    manifests = _provider_manifest_map()
    provider_ids = set(manifests.keys()) | set(_CURATED_PROVIDER_METADATA.keys()) | active_ids
    entries = [
        _merge_provider_entry(provider_id, manifests.get(provider_id))
        for provider_id in provider_ids
    ]
    entries.sort(key=lambda item: (int(item.get("priority", 100)), item["provider_id"]))

    catalog = []
    for entry in entries:
        configured, configuration_source = _provider_is_configured(entry)
        active = entry["provider_id"] in active_ids
        availability = {
            "active": active,
            "available": active,
            "configured": configured,
            "catalog_only": bool(entry.get("catalog_only") and not active),
            "supports_invoke": bool(entry.get("supports_invoke_base") or active),
            "status": _provider_status(entry, active, configured),
            "configuration_source": configuration_source,
            "base_url_hint": entry.get("default_base_url", ""),
        }
        catalog.append(
            {
                "id": entry["provider_id"],
                "provider_id": entry["provider_id"],
                "name": entry["name"],
                "display_name": entry["display_name"],
                "kind": entry["kind"],
                "description": entry["description"],
                "env_vars": list(entry.get("env_vars", [])),
                "base_url_envs": list(entry.get("base_url_envs", [])),
                "default_model": entry.get("default_model", ""),
                "capabilities": list(entry.get("capabilities", [])),
                "availability": availability,
                "metadata": {
                    "catalog_only": bool(entry.get("catalog_only", False)),
                    "supports_invoke": bool(entry.get("supports_invoke_base") or active),
                    "default_base_url": entry.get("default_base_url", ""),
                    "adapter": entry.get("adapter", ""),
                    "entrypoint": entry.get("entrypoint", ""),
                },
            }
        )
    return catalog


def get_provider_catalog_map(active_provider_ids=None):
    return {
        entry["provider_id"]: entry
        for entry in get_provider_catalog(active_provider_ids=active_provider_ids)
    }


def get_provider_availability(provider_id=None, active_provider_ids=None):
    catalog = get_provider_catalog(active_provider_ids=active_provider_ids)
    if provider_id:
        for entry in catalog:
            if entry["provider_id"] == provider_id:
                return dict(entry["availability"])
        return None
    return {entry["provider_id"]: dict(entry["availability"]) for entry in catalog}


def _load_known_models_from_entry(entrypoint: str) -> List[Dict[str, Any]]:
    if not entrypoint:
        return []
    try:
        provider_cls = import_entrypoint(entrypoint)
    except Exception:
        return []
    known_models = getattr(provider_cls, "KNOWN_MODELS", [])
    if not isinstance(known_models, list):
        return []
    return [dict(model) for model in known_models if isinstance(model, dict)]


def _load_models_for_provider(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    provider_id = entry["provider_id"]
    models: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _append(items: Iterable[Dict[str, Any]]) -> None:
        for raw in items:
            if not isinstance(raw, dict):
                continue
            raw_id = str(raw.get("id", "")).strip()
            model_id = str(raw.get("model_id", "")).strip()
            if not raw_id and not model_id:
                continue
            key = raw_id or "{}/{}".format(provider_id, model_id)
            if key in seen:
                continue
            seen.add(key)
            models.append(dict(raw))

    _append(_load_model_manifests(provider_id))
    _append(_load_known_models_from_entry(str(entry.get("entrypoint", ""))))
    _append(_CURATED_PROVIDER_MODELS.get(provider_id, []))
    return models


def _normalize_model_token(value: Any) -> str:
    return str(value or "").strip().lower()


def _annotate_model_collisions(models):
    counts = {}
    for item in models:
        key = _normalize_model_token(item.get("model_id"))
        counts[key] = counts.get(key, 0) + 1

    for item in models:
        key = _normalize_model_token(item.get("model_id"))
        collision_count = counts.get(key, 0)
        has_collision = collision_count > 1
        disambiguated_name = item.get("display_name") or item.get("name") or item.get("model_id")
        if has_collision:
            disambiguated_name = "{} ({})".format(
                item.get("display_name") or item.get("name") or item.get("model_id"),
                item.get("provider_display_name") or item.get("provider_id"),
            )
        item["name_collision"] = has_collision
        item["provider_count_for_model_name"] = collision_count
        item["ambiguity_key"] = key
        item["disambiguated_name"] = disambiguated_name
        metadata = dict(item.get("metadata", {}))
        metadata.update(
            {
                "name_collision": has_collision,
                "provider_count_for_model_name": collision_count,
                "ambiguity_key": key,
                "provider_model_key": item.get("qualified_model_id"),
                "disambiguated_name": disambiguated_name,
            }
        )
        item["metadata"] = metadata
    return models


def get_all_known_models(provider_id=None, active_provider_ids=None):
    catalog_map = get_provider_catalog_map(active_provider_ids=active_provider_ids)
    provider_ids = [provider_id] if provider_id else list(catalog_map.keys())
    models = []

    for current_provider_id in provider_ids:
        provider_entry = catalog_map.get(current_provider_id)
        if provider_entry is None:
            continue
        for raw in _load_models_for_provider(provider_entry["metadata"] | {"provider_id": current_provider_id}):
            model_provider_id = raw.get("provider") or raw.get("provider_id") or current_provider_id
            qualified_model_id = str(raw.get("id", "")).strip()
            model_id = str(raw.get("model_id", "")).strip()
            if qualified_model_id and "/" in qualified_model_id and not model_id:
                _, model_id = qualified_model_id.split("/", 1)
            if not model_id:
                model_id = str(raw.get("model_name") or raw.get("name") or "").strip()
            if not model_id:
                continue
            if not qualified_model_id:
                qualified_model_id = "{}/{}".format(model_provider_id, model_id)
            display_name = str(raw.get("display_name") or raw.get("name") or model_id)
            defaults = dict(raw.get("defaults", {}))
            metadata = dict(raw.get("metadata", {}))
            metadata.update(
                {
                    "provider_model_key": qualified_model_id,
                    "provider_display_name": provider_entry["display_name"],
                    "provider_kind": provider_entry["kind"],
                    "availability_status": provider_entry["availability"].get("status"),
                    "defaults": defaults,
                }
            )
            models.append(
                {
                    "id": qualified_model_id,
                    "qualified_model_id": qualified_model_id,
                    "provider": model_provider_id,
                    "provider_id": model_provider_id,
                    "provider_display_name": provider_entry["display_name"],
                    "model_id": model_id,
                    "model_name": model_id,
                    "name": display_name,
                    "display_name": display_name,
                    "type": str(raw.get("type", "chat")),
                    "context_window": int(raw.get("context_window", 0) or 0),
                    "capabilities": list(raw.get("capabilities", [])),
                    "availability": dict(provider_entry["availability"]),
                    "supports_invoke": bool(provider_entry["availability"].get("supports_invoke", False)),
                    "defaults": defaults,
                    "metadata": metadata,
                }
            )

    deduped: Dict[str, Dict[str, Any]] = {}
    for model in models:
        deduped.setdefault(model["qualified_model_id"], model)
    return _annotate_model_collisions(list(deduped.values()))


def _find_model_entry(models, model_ref="", provider_id="", model_id=""):
    if model_ref:
        for entry in models:
            if entry["qualified_model_id"] == model_ref or entry["id"] == model_ref:
                return entry
    if provider_id and model_id:
        qualified = "{}/{}".format(provider_id, model_id)
        for entry in models:
            if entry["qualified_model_id"] == qualified:
                return entry
    return None


def build_profile_catalog(active_provider_ids=None, custom_profiles=None):
    models = get_all_known_models(active_provider_ids=active_provider_ids)
    profiles = []
    for model in models:
        metadata = dict(model.get("metadata", {}))
        metadata.update(
            {
                "profile_source": "catalog",
                "resolved_model_key": model["qualified_model_id"],
            }
        )
        profiles.append(
            {
                "id": model["qualified_model_id"],
                "profile_id": model["qualified_model_id"],
                "name": model["display_name"],
                "display_name": model["display_name"],
                "provider": model["provider_id"],
                "provider_id": model["provider_id"],
                "provider_display_name": model["provider_display_name"],
                "model": model["model_id"],
                "model_id": model["model_id"],
                "model_name": model["model_name"],
                "qualified_model_id": model["qualified_model_id"],
                "availability": dict(model["availability"]),
                "name_collision": model["name_collision"],
                "provider_count_for_model_name": model["provider_count_for_model_name"],
                "disambiguated_name": model["disambiguated_name"],
                "metadata": metadata,
            }
        )

    for profile_name, raw_profile in (custom_profiles or {}).items():
        if not isinstance(raw_profile, dict):
            continue
        provider_id = raw_profile.get("provider") or raw_profile.get("provider_id", "")
        model_id = raw_profile.get("model") or raw_profile.get("model_id", "")
        resolved = _find_model_entry(
            models,
            model_ref=raw_profile.get("qualified_model_id", ""),
            provider_id=provider_id,
            model_id=model_id,
        )
        if resolved is None and model_id:
            matches = [entry for entry in models if entry["model_id"] == model_id]
            if len(matches) == 1:
                resolved = matches[0]
        availability = dict(resolved["availability"]) if resolved else {"active": False, "available": False}
        metadata = dict(raw_profile.get("metadata", {}))
        metadata.update(
            {
                "profile_source": "custom",
                "resolved_model_key": resolved["qualified_model_id"] if resolved else "",
            }
        )
        profiles.append(
            {
                "id": profile_name,
                "profile_id": profile_name,
                "name": raw_profile.get("display_name") or raw_profile.get("name") or profile_name,
                "display_name": raw_profile.get("display_name") or raw_profile.get("name") or profile_name,
                "provider": provider_id or (resolved["provider_id"] if resolved else ""),
                "provider_id": provider_id or (resolved["provider_id"] if resolved else ""),
                "provider_display_name": resolved["provider_display_name"] if resolved else "",
                "model": model_id or (resolved["model_id"] if resolved else ""),
                "model_id": model_id or (resolved["model_id"] if resolved else ""),
                "model_name": model_id or (resolved["model_id"] if resolved else ""),
                "qualified_model_id": resolved["qualified_model_id"] if resolved else "",
                "availability": availability,
                "name_collision": bool(resolved and resolved["name_collision"]),
                "provider_count_for_model_name": int(
                    resolved["provider_count_for_model_name"] if resolved else 0
                ),
                "disambiguated_name": resolved["disambiguated_name"] if resolved else profile_name,
                "metadata": metadata,
            }
        )
    return profiles


def _load_legacy_providers() -> Dict[str, Any]:
    available = {}
    for env_var, provider_id, module_path, class_name in _LEGACY_PROVIDER_REGISTRY:
        if not _truthy_env(env_var):
            continue
        try:
            module = importlib.import_module(module_path)
            provider_cls = getattr(module, class_name)
            available[provider_id] = provider_cls()
        except Exception:
            continue
    return available


def _credentials_ready(manifest: Dict[str, Any], provider_id: str) -> bool:
    if provider_id == "stub":
        return True
    if provider_id == "rumi":
        return False
    api_envs = _manifest_env_list(
        manifest.get("api_key_env"),
        _CURATED_PROVIDER_METADATA.get(provider_id, {}).get("env_vars", []),
    )
    base_url_envs = _manifest_env_list(
        manifest.get("base_url_env"),
        _CURATED_PROVIDER_METADATA.get(provider_id, {}).get("base_url_envs", []),
    )
    if any(_truthy_env(name) for name in api_envs + base_url_envs):
        return True
    if not bool(manifest.get("credential_required", True)):
        return not api_envs and not base_url_envs
    return False


def _instantiate_manifest_provider(manifest: Dict[str, Any]):
    provider_id = str(manifest.get("id", "")).strip()
    if not provider_id or provider_id == "rumi":
        return None

    adapter = str(manifest.get("adapter", "")).strip()
    entrypoint = str(manifest.get("entrypoint", "")).strip()
    if adapter == "openai_compatible":
        return OpenAICompatibleProvider.from_manifest(
            manifest,
            model_manifests=_load_model_manifests(provider_id),
        )
    if entrypoint:
        provider_cls = import_entrypoint(entrypoint)
        return provider_cls()
    return None


def detect_available_providers():
    """Detect manifest-driven runtime providers, then fall back to legacy shims."""
    available = {}
    manifests = _provider_manifest_map()
    for provider_id, manifest in manifests.items():
        if not _credentials_ready(manifest, provider_id):
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
    """Create the rumi meta-provider when a non-stub provider is active."""
    non_stub = [name for name in client._providers if name != "stub"]
    if not non_stub:
        return None

    manifest = _provider_manifest_map().get("rumi", {})
    entrypoint = str(manifest.get("entrypoint", "")).strip()
    if entrypoint:
        try:
            provider_cls = import_entrypoint(entrypoint)
            return provider_cls(client)
        except Exception:
            return None

    try:
        from .rumi_provider import RumiProvider

        return RumiProvider(client)
    except Exception:
        return None


def get_best_model_for_provider(name, use_case="chat"):
    """Return the preferred default model id for the provider."""
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
    return _BEST_MODEL_BY_PROVIDER.get(name)
