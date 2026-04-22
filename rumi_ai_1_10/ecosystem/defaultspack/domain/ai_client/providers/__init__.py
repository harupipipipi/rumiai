import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

"""
providers package - provider discovery and catalog helpers.

This module keeps the runtime detection helpers small while exposing a richer
provider/model catalog for the defaultspack backend surface.
"""


_PROVIDER_CLASS_REGISTRY = [
    ("OPENAI_API_KEY", "openai", "domain.ai_client.providers.openai_provider", "OpenAIProvider"),
    ("ANTHROPIC_API_KEY", "anthropic", "domain.ai_client.providers.anthropic_provider", "AnthropicProvider"),
    ("GOOGLE_API_KEY", "google", "domain.ai_client.providers.google_provider", "GoogleProvider"),
    ("GENSPARK_API_KEY", "genspark", "domain.ai_client.providers.genspark_provider", "GensparkProvider"),
]

_OPENAI_COMPATIBLE_RUNTIME_SPECS = [
    ("xai", ("XAI_API_KEY",), ("XAI_BASE_URL",), "https://api.x.ai/v1"),
    ("mistral", ("MISTRAL_API_KEY",), ("MISTRAL_BASE_URL",), "https://api.mistral.ai/v1"),
    ("groq", ("GROQ_API_KEY",), ("GROQ_BASE_URL",), "https://api.groq.com/openai/v1"),
    ("deepseek", ("DEEPSEEK_API_KEY",), ("DEEPSEEK_BASE_URL",), "https://api.deepseek.com/v1"),
    ("openrouter", ("OPENROUTER_API_KEY",), ("OPENROUTER_BASE_URL",), "https://openrouter.ai/api/v1"),
    ("together", ("TOGETHER_API_KEY",), ("TOGETHER_BASE_URL",), "https://api.together.xyz/v1"),
    ("fireworks", ("FIREWORKS_API_KEY",), ("FIREWORKS_BASE_URL",), "https://api.fireworks.ai/inference/v1"),
    ("perplexity", ("PERPLEXITY_API_KEY",), ("PERPLEXITY_BASE_URL",), "https://api.perplexity.ai"),
    ("ollama", (), ("OLLAMA_BASE_URL", "OLLAMA_HOST"), "http://127.0.0.1:11434/v1"),
    ("lmstudio", (), ("LMSTUDIO_BASE_URL",), "http://127.0.0.1:1234/v1"),
    ("vllm", (), ("VLLM_BASE_URL",), "http://127.0.0.1:8000/v1"),
    ("llamacpp", (), ("LLAMACPP_BASE_URL",), "http://127.0.0.1:8080/v1"),
]

_KNOWN_MODEL_CLASSES = {
    "openai": ("domain.ai_client.providers.openai_provider", "OpenAIProvider"),
    "anthropic": ("domain.ai_client.providers.anthropic_provider", "AnthropicProvider"),
    "google": ("domain.ai_client.providers.google_provider", "GoogleProvider"),
    "genspark": ("domain.ai_client.providers.genspark_provider", "GensparkProvider"),
    "stub": ("domain.ai_client.providers.stub_provider", "StubProvider"),
    "rumi": ("domain.ai_client.providers.rumi_provider", "RumiProvider"),
}

_PROVIDER_SPECS = [
    {
        "id": "stub",
        "name": "Stub",
        "kind": "builtin",
        "description": "Built-in test provider for deterministic responses.",
        "env_vars": [],
        "base_url_envs": [],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "default",
        "capabilities": ["chat", "embedding", "image", "transcription", "tts"],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "kind": "cloud",
        "description": "OpenAI hosted models and multimodal APIs.",
        "env_vars": ["OPENAI_API_KEY"],
        "base_url_envs": ["OPENAI_BASE_URL"],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "gpt-4o",
        "capabilities": ["chat", "tool_calls", "vision", "embedding", "image", "transcription", "tts"],
    },
    {
        "id": "anthropic",
        "name": "Anthropic",
        "kind": "cloud",
        "description": "Anthropic Claude models.",
        "env_vars": ["ANTHROPIC_API_KEY"],
        "base_url_envs": ["ANTHROPIC_BASE_URL"],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "claude-sonnet-4-0",
        "capabilities": ["chat", "tool_calls", "vision", "reasoning"],
    },
    {
        "id": "google",
        "name": "Google",
        "kind": "cloud",
        "description": "Google Gemini and multimodal APIs.",
        "env_vars": ["GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"],
        "base_url_envs": [],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "gemini-2.5-pro",
        "capabilities": ["chat", "tool_calls", "vision", "embedding"],
    },
    {
        "id": "genspark",
        "name": "Genspark",
        "kind": "cloud",
        "description": "Genspark OpenAI-compatible hosted models.",
        "env_vars": ["GENSPARK_API_KEY", "OPENAI_API_KEY"],
        "base_url_envs": ["GENSPARK_LLM_BASE_URL", "OPENAI_BASE_URL"],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "gpt-5-mini",
        "capabilities": ["chat", "tool_calls", "vision"],
    },
    {
        "id": "groq",
        "name": "Groq",
        "kind": "cloud",
        "description": "Fast hosted inference for open-weight models.",
        "env_vars": ["GROQ_API_KEY"],
        "base_url_envs": ["GROQ_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "llama-3.3-70b-versatile",
        "capabilities": ["chat", "tool_calls"],
    },
    {
        "id": "mistral",
        "name": "Mistral",
        "kind": "cloud",
        "description": "Mistral hosted models.",
        "env_vars": ["MISTRAL_API_KEY"],
        "base_url_envs": ["MISTRAL_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "mistral-large-latest",
        "capabilities": ["chat", "embedding"],
    },
    {
        "id": "xai",
        "name": "xAI",
        "kind": "cloud",
        "description": "xAI Grok models.",
        "env_vars": ["XAI_API_KEY"],
        "base_url_envs": ["XAI_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "grok-2-latest",
        "capabilities": ["chat", "vision"],
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "kind": "aggregator",
        "description": "Aggregator for many provider-backed models.",
        "env_vars": ["OPENROUTER_API_KEY"],
        "base_url_envs": ["OPENROUTER_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "gpt-4o-mini",
        "capabilities": ["chat", "tool_calls", "vision"],
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "kind": "cloud",
        "description": "DeepSeek chat and reasoning models.",
        "env_vars": ["DEEPSEEK_API_KEY"],
        "base_url_envs": ["DEEPSEEK_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "deepseek-chat",
        "capabilities": ["chat", "reasoning"],
    },
    {
        "id": "perplexity",
        "name": "Perplexity",
        "kind": "cloud",
        "description": "Perplexity online and sonar models.",
        "env_vars": ["PERPLEXITY_API_KEY"],
        "base_url_envs": ["PERPLEXITY_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "sonar-pro",
        "capabilities": ["chat", "search"],
    },
    {
        "id": "together",
        "name": "Together",
        "kind": "cloud",
        "description": "Hosted inference for open models.",
        "env_vars": ["TOGETHER_API_KEY"],
        "base_url_envs": ["TOGETHER_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "llama-3.1-70b-instruct-turbo",
        "capabilities": ["chat", "tool_calls"],
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "kind": "local",
        "description": "Local models served by Ollama.",
        "env_vars": [],
        "base_url_envs": ["OLLAMA_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "llama3.1:8b",
        "default_base_url": "http://127.0.0.1:11434",
        "capabilities": ["chat", "embedding", "local"],
    },
    {
        "id": "lmstudio",
        "name": "LM Studio",
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
    {
        "id": "vllm",
        "name": "vLLM",
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
    {
        "id": "openai_compatible",
        "name": "OpenAI Compatible",
        "kind": "custom",
        "description": "Generic OpenAI-compatible endpoint.",
        "env_vars": ["OPENAI_COMPATIBLE_API_KEY"],
        "base_url_envs": ["OPENAI_COMPATIBLE_BASE_URL"],
        "catalog_only": True,
        "supports_invoke": False,
        "default_model": "gpt-oss-20b",
        "capabilities": ["chat", "tool_calls", "embedding", "openai_compatible"],
    },
    {
        "id": "rumi",
        "name": "Rumi",
        "kind": "meta",
        "description": "Meta-provider for routing and orchestration.",
        "env_vars": [],
        "base_url_envs": [],
        "catalog_only": False,
        "supports_invoke": True,
        "default_model": "default",
        "capabilities": ["chat", "routing", "meta"],
    },
]

_CURATED_PROVIDER_MODELS = {
    "stub": [
        {"model_id": "default", "name": "Stub Default Model", "type": "chat"},
        {"model_id": "fast", "name": "Stub Fast Model", "type": "chat"},
        {"model_id": "large", "name": "Stub Large Model", "type": "chat"},
    ],
    "groq": [
        {"model_id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B Versatile", "type": "chat"},
        {"model_id": "qwen-qwq-32b", "name": "QWQ 32B", "type": "reasoning"},
        {"model_id": "deepseek-r1-distill-llama-70b", "name": "DeepSeek R1 Distill Llama 70B", "type": "reasoning"},
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
    "openai_compatible": [
        {"model_id": "gpt-oss-20b", "name": "GPT OSS 20B", "type": "chat"},
        {"model_id": "deepseek-r1", "name": "DeepSeek R1", "type": "reasoning"},
    ],
}

_PROVIDER_SPEC_BY_ID = {spec["id"]: spec for spec in _PROVIDER_SPECS}
_BEST_MODEL_BY_PROVIDER = {
    "stub": "default",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-0",
    "google": "gemini-2.5-pro",
    "genspark": "gpt-5-mini",
    "groq": "llama-3.3-70b-versatile",
    "mistral": "mistral-large-latest",
    "xai": "grok-2-latest",
    "openrouter": "gpt-4o-mini",
    "deepseek": "deepseek-reasoner",
    "perplexity": "sonar-pro",
    "together": "llama-3.1-70b-instruct-turbo",
    "ollama": "llama3.1:8b",
    "lmstudio": "deepseek-r1",
    "vllm": "deepseek-r1",
    "openai_compatible": "gpt-oss-20b",
    "rumi": "default",
}


def _load_provider_class(module_path, class_name):
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)
    except Exception:
        return None


def _truthy_env(env_name):
    return bool(str(os.environ.get(env_name, "") or "").strip())


def _provider_is_configured(spec):
    for env_name in spec.get("env_vars", []):
        if _truthy_env(env_name):
            return True, env_name
    for env_name in spec.get("base_url_envs", []):
        if _truthy_env(env_name):
            return True, env_name
    if spec.get("kind") == "local" and spec.get("default_base_url"):
        return True, "default_local_endpoint"
    if spec["id"] == "stub":
        return True, "builtin"
    return False, None


def _normalize_model_token(value):
    return str(value or "").strip().lower()


def _provider_status(spec, active, configured):
    if active:
        return "active"
    if spec.get("catalog_only"):
        return "catalog_only"
    if configured:
        return "configured"
    return "unconfigured"


def _first_env_value(names):
    for env_name in names:
        value = str(os.environ.get(env_name, "") or "").strip()
        if value:
            return value
    return ""


def get_provider_catalog(active_provider_ids=None):
    active_ids = set(active_provider_ids or [])
    catalog = []
    for spec in _PROVIDER_SPECS:
        configured, configuration_source = _provider_is_configured(spec)
        active = spec["id"] in active_ids
        availability = {
            "active": active,
            "available": active,
            "configured": configured,
            "catalog_only": bool(spec.get("catalog_only", False) and not active),
            "supports_invoke": bool(spec.get("supports_invoke", False) or active),
            "status": _provider_status(spec, active, configured),
            "configuration_source": configuration_source,
            "base_url_hint": spec.get("default_base_url", ""),
        }
        catalog.append(
            {
                "id": spec["id"],
                "provider_id": spec["id"],
                "name": spec["name"],
                "display_name": spec["name"],
                "kind": spec.get("kind", "cloud"),
                "description": spec.get("description", ""),
                "env_vars": list(spec.get("env_vars", [])),
                "base_url_envs": list(spec.get("base_url_envs", [])),
                "default_model": spec.get("default_model", ""),
                "capabilities": list(spec.get("capabilities", [])),
                "availability": availability,
                "metadata": {
                    "catalog_only": bool(spec.get("catalog_only", False)),
                    "supports_invoke": bool(spec.get("supports_invoke", False) or active),
                    "default_base_url": spec.get("default_base_url", ""),
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


def _load_known_models_from_class(provider_id):
    module_info = _KNOWN_MODEL_CLASSES.get(provider_id)
    if not module_info:
        return []
    module_path, class_name = module_info
    provider_cls = _load_provider_class(module_path, class_name)
    if provider_cls is None:
        return []
    return list(getattr(provider_cls, "KNOWN_MODELS", []))


def _load_models_for_provider(provider_id):
    models = _load_known_models_from_class(provider_id)
    if models:
        return models
    return list(_CURATED_PROVIDER_MODELS.get(provider_id, []))


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
    provider_ids = [provider_id] if provider_id else [spec["id"] for spec in _PROVIDER_SPECS]
    models = []

    for current_provider_id in provider_ids:
        provider_entry = catalog_map.get(current_provider_id)
        if provider_entry is None:
            continue
        provider_models = _load_models_for_provider(current_provider_id)
        for raw in provider_models:
            model_provider_id = raw.get("provider") or raw.get("provider_id") or current_provider_id
            qualified_model_id = raw.get("id", "")
            model_id = raw.get("model_id", "")
            if qualified_model_id and "/" in qualified_model_id and not model_id:
                _, model_id = qualified_model_id.split("/", 1)
            if not model_id:
                model_id = raw.get("model_name") or raw.get("name", "")
            if not qualified_model_id:
                qualified_model_id = "{}/{}".format(model_provider_id, model_id)
            display_name = raw.get("display_name") or raw.get("name") or model_id
            availability = dict(provider_entry["availability"])
            model_payload = {
                "id": qualified_model_id,
                "qualified_model_id": qualified_model_id,
                "provider": model_provider_id,
                "provider_id": model_provider_id,
                "provider_display_name": provider_entry["display_name"],
                "model_id": model_id,
                "model_name": model_id,
                "name": display_name,
                "display_name": display_name,
                "type": raw.get("type", "chat"),
                "context_window": int(raw.get("context_window", 0) or 0),
                "capabilities": list(raw.get("capabilities", [])),
                "availability": availability,
                "supports_invoke": bool(availability.get("supports_invoke", False)),
                "metadata": dict(raw.get("metadata", {})),
            }
            model_payload["metadata"].update(
                {
                    "provider_model_key": qualified_model_id,
                    "provider_display_name": provider_entry["display_name"],
                    "provider_kind": provider_entry["kind"],
                    "availability_status": availability.get("status"),
                }
            )
            models.append(model_payload)

    return _annotate_model_collisions(models)


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


def detect_available_providers():
    """Detect runtime-enabled providers and return {provider_id: instance}."""
    available = {}
    for env_var, provider_id, module_path, class_name in _PROVIDER_CLASS_REGISTRY:
        if not _truthy_env(env_var):
            continue
        provider_cls = _load_provider_class(module_path, class_name)
        if provider_cls is None:
            continue
        try:
            available[provider_id] = provider_cls()
        except Exception:
            continue
    try:
        from domain.ai_client.providers.openai_compatible_provider import (
            OpenAICompatibleProvider,
        )
        from ecosystem.defaultspack.backend.ai_client.provider_catalog import (
            list_model_catalog,
        )

        for provider_id, key_envs, base_url_envs, default_base_url in _OPENAI_COMPATIBLE_RUNTIME_SPECS:
            api_key = _first_env_value(key_envs)
            base_url = _first_env_value(base_url_envs)
            if not api_key and not base_url:
                continue
            known_models = list_model_catalog(provider=provider_id)
            try:
                available[provider_id] = OpenAICompatibleProvider(
                    api_key=api_key,
                    base_url=base_url or default_base_url,
                    known_models=known_models,
                )
            except Exception:
                continue
    except Exception:
        pass
    return available


def detect_rumi_provider(client):
    """Create the rumi meta-provider when a non-stub provider is active."""
    non_stub = [name for name in client._providers if name != "stub"]
    if not non_stub:
        return None
    provider_cls = _load_provider_class(
        "domain.ai_client.providers.rumi_provider",
        "RumiProvider",
    )
    if provider_cls is None:
        return None
    try:
        return provider_cls(client)
    except Exception:
        return None


def get_best_model_for_provider(name):
    """Return the preferred default model id for the provider."""
    return _BEST_MODEL_BY_PROVIDER.get(name)
