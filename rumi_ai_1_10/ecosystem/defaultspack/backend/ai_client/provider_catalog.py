"""Catalog and availability helpers for defaultspack AI providers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ProviderCatalogEntry:
    provider_id: str
    display_name: str
    category: str
    description: str
    env_vars: Tuple[str, ...] = ()
    local: bool = False
    openai_compatible: bool = False
    capabilities: Tuple[str, ...] = ()
    aliases: Tuple[str, ...] = ()
    module_path: str = ""
    class_name: str = ""
    base_url_envs: Tuple[str, ...] = ()


_PROVIDER_CATALOG: Tuple[ProviderCatalogEntry, ...] = (
    ProviderCatalogEntry(
        provider_id="openai",
        display_name="OpenAI",
        category="major",
        description="OpenAI Responses/chat/image/audio family.",
        env_vars=("OPENAI_API_KEY",),
        capabilities=("chat", "stream", "vision", "embedding", "image", "audio", "reasoning"),
        aliases=("azure_openai",),
        module_path="domain.ai_client.providers.openai_provider",
        class_name="OpenAIProvider",
        base_url_envs=("OPENAI_BASE_URL", "AZURE_OPENAI_ENDPOINT"),
    ),
    ProviderCatalogEntry(
        provider_id="anthropic",
        display_name="Anthropic",
        category="major",
        description="Claude family with strong coding and reasoning.",
        env_vars=("ANTHROPIC_API_KEY",),
        capabilities=("chat", "stream", "vision", "reasoning", "tool_use"),
        module_path="domain.ai_client.providers.anthropic_provider",
        class_name="AnthropicProvider",
        base_url_envs=("ANTHROPIC_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="google",
        display_name="Google",
        category="major",
        description="Gemini family via Google Generative AI APIs.",
        env_vars=("GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"),
        capabilities=("chat", "stream", "vision", "embedding", "image", "audio", "reasoning", "large_context"),
        aliases=("vertexai",),
        module_path="domain.ai_client.providers.google_provider",
        class_name="GoogleProvider",
        base_url_envs=("GOOGLE_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="genspark",
        display_name="Genspark",
        category="minor",
        description="OpenAI-compatible gateway used by some coding workflows.",
        env_vars=("GENSPARK_API_KEY",),
        openai_compatible=True,
        capabilities=("chat", "stream", "reasoning", "tool_use"),
        module_path="domain.ai_client.providers.genspark_provider",
        class_name="GensparkProvider",
        base_url_envs=("GENSPARK_LLM_BASE_URL", "OPENAI_BASE_URL"),
    ),
    ProviderCatalogEntry(
        provider_id="xai",
        display_name="xAI",
        category="minor",
        description="Grok models via OpenAI-compatible endpoints.",
        env_vars=("XAI_API_KEY",),
        openai_compatible=True,
        capabilities=("chat", "stream", "vision", "reasoning"),
        base_url_envs=("XAI_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="mistral",
        display_name="Mistral",
        category="minor",
        description="Mistral hosted model APIs.",
        env_vars=("MISTRAL_API_KEY",),
        openai_compatible=True,
        capabilities=("chat", "stream", "embedding", "tool_use"),
        base_url_envs=("MISTRAL_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="groq",
        display_name="Groq",
        category="minor",
        description="Fast hosted inference via OpenAI-compatible APIs.",
        env_vars=("GROQ_API_KEY",),
        openai_compatible=True,
        capabilities=("chat", "stream", "tool_use"),
        base_url_envs=("GROQ_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="cohere",
        display_name="Cohere",
        category="minor",
        description="Cohere Command family and rerank APIs.",
        env_vars=("COHERE_API_KEY",),
        capabilities=("chat", "stream", "embedding", "rerank", "tool_use"),
        base_url_envs=("COHERE_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="deepseek",
        display_name="DeepSeek",
        category="minor",
        description="DeepSeek models via hosted OpenAI-compatible API.",
        env_vars=("DEEPSEEK_API_KEY",),
        openai_compatible=True,
        capabilities=("chat", "stream", "reasoning", "tool_use"),
        base_url_envs=("DEEPSEEK_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="openrouter",
        display_name="OpenRouter",
        category="gateway",
        description="Multi-provider gateway with normalized model IDs.",
        env_vars=("OPENROUTER_API_KEY",),
        openai_compatible=True,
        capabilities=("chat", "stream", "vision", "reasoning", "tool_use"),
        base_url_envs=("OPENROUTER_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="together",
        display_name="Together",
        category="gateway",
        description="Hosted inference across many open-weight models.",
        env_vars=("TOGETHER_API_KEY",),
        openai_compatible=True,
        capabilities=("chat", "stream", "vision", "image", "embedding", "tool_use"),
        base_url_envs=("TOGETHER_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="fireworks",
        display_name="Fireworks",
        category="gateway",
        description="Hosted inference and image APIs for open models.",
        env_vars=("FIREWORKS_API_KEY",),
        openai_compatible=True,
        capabilities=("chat", "stream", "vision", "image", "embedding", "tool_use"),
        base_url_envs=("FIREWORKS_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="perplexity",
        display_name="Perplexity",
        category="gateway",
        description="Perplexity hosted models with OpenAI-compatible surface.",
        env_vars=("PERPLEXITY_API_KEY",),
        openai_compatible=True,
        capabilities=("chat", "stream", "reasoning"),
        base_url_envs=("PERPLEXITY_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="replicate",
        display_name="Replicate",
        category="gateway",
        description="Replicate hosted model runtime.",
        env_vars=("REPLICATE_API_TOKEN",),
        capabilities=("chat", "stream", "image", "audio", "video"),
        base_url_envs=("REPLICATE_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="ollama",
        display_name="Ollama",
        category="local",
        description="Local LLM runtime with OpenAI-compatible and native APIs.",
        env_vars=("OLLAMA_HOST",),
        local=True,
        openai_compatible=True,
        capabilities=("chat", "stream", "embedding", "tool_use", "offline"),
        base_url_envs=("OLLAMA_BASE_URL", "OLLAMA_HOST"),
    ),
    ProviderCatalogEntry(
        provider_id="lmstudio",
        display_name="LM Studio",
        category="local",
        description="Local OpenAI-compatible model server from LM Studio.",
        env_vars=("LMSTUDIO_BASE_URL",),
        local=True,
        openai_compatible=True,
        capabilities=("chat", "stream", "embedding", "tool_use", "offline"),
        base_url_envs=("LMSTUDIO_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="vllm",
        display_name="vLLM",
        category="local",
        description="Self-hosted OpenAI-compatible inference server.",
        env_vars=("VLLM_BASE_URL",),
        local=True,
        openai_compatible=True,
        capabilities=("chat", "stream", "embedding", "tool_use"),
        base_url_envs=("VLLM_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="llamacpp",
        display_name="llama.cpp",
        category="local",
        description="Local inference server, often OpenAI-compatible.",
        env_vars=("LLAMACPP_BASE_URL",),
        local=True,
        openai_compatible=True,
        capabilities=("chat", "stream", "embedding", "offline"),
        base_url_envs=("LLAMACPP_BASE_URL",),
    ),
    ProviderCatalogEntry(
        provider_id="rumi",
        display_name="Rumi Router",
        category="meta",
        description="Meta-provider for routing, pipelines, and MoA flows.",
        capabilities=("chat", "stream", "routing", "meta", "tool_use"),
    ),
    ProviderCatalogEntry(
        provider_id="stub",
        display_name="Stub",
        category="test",
        description="Deterministic test-only provider.",
        capabilities=("chat", "stream", "embedding", "image", "audio"),
        module_path="domain.ai_client.providers.stub_provider",
        class_name="StubProvider",
    ),
)


_CANONICAL_MODEL_NAMES: Dict[str, str] = {
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt-4": "gpt-4",
    "gpt-3.5-turbo": "gpt-3.5-turbo",
    "o1": "o1",
    "o1-mini": "o1-mini",
    "o3-mini": "o3-mini",
    "gpt-5": "gpt-5",
    "gpt-5.1": "gpt-5.1",
    "gpt-5.2": "gpt-5.2",
    "gpt-5-mini": "gpt-5-mini",
    "gpt-5-nano": "gpt-5-nano",
    "gpt-5-codex": "gpt-5-codex",
    "gpt-5.2-codex": "gpt-5.2-codex",
    "claude-opus-4-0": "claude-opus-4",
    "claude-sonnet-4-0": "claude-sonnet-4",
    "claude-3-5-sonnet-20241022": "claude-3.5-sonnet",
    "claude-3-5-haiku-20241022": "claude-3.5-haiku",
    "claude-3-opus-20240229": "claude-3-opus",
    "claude-3-haiku-20240307": "claude-3-haiku",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.0-flash": "gemini-2.0-flash",
    "gemini-1.5-pro": "gemini-1.5-pro",
    "gemini-1.5-flash": "gemini-1.5-flash",
    "text-embedding-004": "text-embedding-004",
    "text-embedding-3-small": "text-embedding-3-small",
    "text-embedding-3-large": "text-embedding-3-large",
    "dall-e-3": "dall-e-3",
    "whisper-1": "whisper-1",
    "tts-1": "tts-1",
    "tts-1-hd": "tts-1-hd",
    "openai/gpt-4o": "gpt-4o",
    "openai/gpt-4o-mini": "gpt-4o-mini",
    "anthropic/claude-3.5-sonnet": "claude-3.5-sonnet",
    "DeepSeek-R1": "deepseek-r1",
    "deepseek-reasoner": "deepseek-r1",
}


_CATALOG_MODELS: Dict[str, Tuple[Dict[str, Any], ...]] = {
    "stub": (
        {"id": "stub/default", "name": "Stub Default Model", "provider": "stub", "type": "chat"},
        {"id": "stub/fast", "name": "Stub Fast Model", "provider": "stub", "type": "chat"},
        {"id": "stub/large", "name": "Stub Large Model", "provider": "stub", "type": "chat"},
    ),
    "xai": (
        {"id": "xai/grok-2-latest", "name": "Grok 2", "provider": "xai", "type": "chat"},
        {"id": "xai/grok-2-vision-latest", "name": "Grok 2 Vision", "provider": "xai", "type": "chat"},
    ),
    "mistral": (
        {"id": "mistral/mistral-large-latest", "name": "Mistral Large", "provider": "mistral", "type": "chat"},
        {"id": "mistral/codestral-latest", "name": "Codestral", "provider": "mistral", "type": "chat"},
    ),
    "groq": (
        {"id": "groq/llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "provider": "groq", "type": "chat"},
        {"id": "groq/qwen-qwq-32b", "name": "Qwen QwQ 32B", "provider": "groq", "type": "chat"},
    ),
    "cohere": (
        {"id": "cohere/command-r-plus", "name": "Command R+", "provider": "cohere", "type": "chat"},
        {"id": "cohere/embed-v3", "name": "Embed v3", "provider": "cohere", "type": "embedding"},
    ),
    "deepseek": (
        {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat", "provider": "deepseek", "type": "chat"},
        {"id": "deepseek/deepseek-reasoner", "name": "DeepSeek Reasoner", "provider": "deepseek", "type": "chat"},
    ),
    "openrouter": (
        {"id": "openrouter/openai/gpt-4o", "name": "GPT-4o via OpenRouter", "provider": "openrouter", "type": "chat"},
        {"id": "openrouter/anthropic/claude-3.5-sonnet", "name": "Claude Sonnet via OpenRouter", "provider": "openrouter", "type": "chat"},
    ),
    "together": (
        {"id": "together/meta-llama/Llama-3.3-70B-Instruct-Turbo", "name": "Llama 3.3 70B Turbo", "provider": "together", "type": "chat"},
        {"id": "together/deepseek-ai/DeepSeek-R1", "name": "DeepSeek R1", "provider": "together", "type": "chat"},
    ),
    "fireworks": (
        {"id": "fireworks/accounts/fireworks/models/llama-v3p1-70b-instruct", "name": "Llama 3.1 70B", "provider": "fireworks", "type": "chat"},
    ),
    "perplexity": (
        {"id": "perplexity/sonar-reasoning-pro", "name": "Sonar Reasoning Pro", "provider": "perplexity", "type": "chat"},
    ),
    "replicate": (
        {"id": "replicate/meta/meta-llama-3-70b-instruct", "name": "Llama 3 70B", "provider": "replicate", "type": "chat"},
    ),
    "ollama": (
        {"id": "ollama/llama3.2", "name": "Llama 3.2", "provider": "ollama", "type": "chat"},
        {"id": "ollama/qwen2.5-coder", "name": "Qwen 2.5 Coder", "provider": "ollama", "type": "chat"},
    ),
    "lmstudio": (
        {"id": "lmstudio/local-model", "name": "Local Model", "provider": "lmstudio", "type": "chat"},
    ),
    "vllm": (
        {"id": "vllm/local-openai-compatible", "name": "Local OpenAI-Compatible", "provider": "vllm", "type": "chat"},
    ),
    "llamacpp": (
        {"id": "llamacpp/local-gguf", "name": "Local GGUF Model", "provider": "llamacpp", "type": "chat"},
    ),
    "rumi": (
        {"id": "rumi/router", "name": "Rumi Router", "provider": "rumi", "type": "chat"},
        {"id": "rumi/pipeline", "name": "Rumi Pipeline", "provider": "rumi", "type": "chat"},
        {"id": "rumi/moa", "name": "Rumi MoA", "provider": "rumi", "type": "chat"},
    ),
}


def _env_detected(entry: ProviderCatalogEntry) -> Tuple[bool, List[str]]:
    configured = [name for name in entry.env_vars if os.environ.get(name)]
    if entry.local:
        if configured:
            return True, configured
        base_url_env = [name for name in entry.base_url_envs if os.environ.get(name)]
        if base_url_env:
            return True, base_url_env
    return bool(configured), configured


def _load_known_models(entry: ProviderCatalogEntry) -> List[Dict[str, Any]]:
    if entry.module_path and entry.class_name:
        try:
            mod = import_module(entry.module_path)
            provider_cls = getattr(mod, entry.class_name)
            known_models = getattr(provider_cls, "KNOWN_MODELS", [])
            if isinstance(known_models, Sequence):
                loaded = [dict(model) for model in known_models if isinstance(model, dict)]
                if loaded:
                    return loaded
        except Exception:
            pass
    return [dict(model) for model in _CATALOG_MODELS.get(entry.provider_id, ())]


def _normalize_model_payload(model: Dict[str, Any], entry: ProviderCatalogEntry, detected: bool) -> Dict[str, Any]:
    provider_id = model.get("provider", entry.provider_id)
    raw_id = str(model.get("id", "") or "")
    model_id = raw_id.split("/", 1)[1] if raw_id.startswith(provider_id + "/") else (model.get("model_id") or raw_id)
    canonical_source = model_id.rsplit("/", 1)[-1]
    canonical_model_id = _CANONICAL_MODEL_NAMES.get(model_id, _CANONICAL_MODEL_NAMES.get(canonical_source, canonical_source))
    availability = {
        "configured": detected,
        "active": False,
        "available": detected,
        "status": "configured" if detected else ("local" if entry.local else "catalog"),
        "catalog_only": not bool(entry.module_path and entry.class_name),
        "local": entry.local,
    }
    return {
        **model,
        "id": raw_id or f"{provider_id}/{model_id}",
        "provider": provider_id,
        "provider_id": provider_id,
        "model_id": model_id,
        "canonical_model_id": canonical_model_id,
        "family_id": canonical_model_id,
        "qualified_model_id": raw_id or f"{provider_id}/{model_id}",
        "same_model_across_providers_key": canonical_model_id,
        "availability": availability,
        "provider_category": entry.category,
        "provider_local": entry.local,
        "metadata": {
            "provider_model_key": raw_id or f"{provider_id}/{model_id}",
            "provider_display_name": entry.display_name,
            "provider_category": entry.category,
            "provider_local": entry.local,
        },
    }


def _annotate_model_collisions(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    collision_counts: Dict[str, int] = {}
    for model in models:
        key = str(model.get("same_model_across_providers_key", "") or "").strip().lower()
        if not key:
            continue
        collision_counts[key] = collision_counts.get(key, 0) + 1

    for model in models:
        key = str(model.get("same_model_across_providers_key", "") or "").strip().lower()
        collision_count = collision_counts.get(key, 0)
        has_collision = collision_count > 1
        display_name = model.get("name") or model.get("display_name") or model.get("model_id")
        model["name_collision"] = has_collision
        model["provider_count_for_model_name"] = collision_count
        model["ambiguity_key"] = key
        model["disambiguated_name"] = (
            "{} ({})".format(display_name, model.get("provider_id", ""))
            if has_collision
            else display_name
        )
        metadata = dict(model.get("metadata", {}))
        metadata.update(
            {
                "name_collision": has_collision,
                "provider_count_for_model_name": collision_count,
                "ambiguity_key": key,
                "disambiguated_name": model["disambiguated_name"],
            }
        )
        model["metadata"] = metadata
    return models


def list_provider_catalog() -> List[Dict[str, Any]]:
    providers: List[Dict[str, Any]] = []
    for entry in _PROVIDER_CATALOG:
        detected, configured_envs = _env_detected(entry)
        providers.append(
            {
                "provider_id": entry.provider_id,
                "id": entry.provider_id,
                "display_name": entry.display_name,
                "name": entry.display_name,
                "category": entry.category,
                "description": entry.description,
                "env_vars": list(entry.env_vars),
                "configured_envs": configured_envs,
                "configured": detected,
                "local": entry.local,
                "openai_compatible": entry.openai_compatible,
                "capabilities": list(entry.capabilities),
                "aliases": list(entry.aliases),
                "base_url_envs": list(entry.base_url_envs),
                "status": "configured" if detected else "available",
                "availability": {
                    "configured": detected,
                    "active": False,
                    "available": detected,
                    "status": "configured" if detected else "available",
                    "catalog_only": not bool(entry.module_path and entry.class_name),
                    "local": entry.local,
                },
            }
        )
    return providers


def list_model_catalog(provider: str = "") -> List[Dict[str, Any]]:
    models: List[Dict[str, Any]] = []
    for entry in _PROVIDER_CATALOG:
        if provider and entry.provider_id != provider:
            continue
        detected, _ = _env_detected(entry)
        seen: set[str] = set()
        for model in _load_known_models(entry):
            payload = _normalize_model_payload(model, entry, detected)
            key = payload["qualified_model_id"]
            if key in seen:
                continue
            seen.add(key)
            models.append(payload)
    return _annotate_model_collisions(models)


def list_profile_catalog() -> List[Dict[str, Any]]:
    profiles: List[Dict[str, Any]] = []
    for model in list_model_catalog():
        profiles.append(
            {
                "profile_id": model["qualified_model_id"],
                "display_name": model.get("name") or model.get("display_name") or model["model_id"],
                "provider_id": model["provider_id"],
                "model_id": model["model_id"],
                "canonical_model_id": model["canonical_model_id"],
                "family_id": model["family_id"],
                "qualified_model_id": model["qualified_model_id"],
                "same_model_across_providers_key": model["same_model_across_providers_key"],
                "availability": model["availability"],
                "provider_category": model["provider_category"],
                "local": model["provider_local"],
                "source": "catalog",
                "name_collision": model["name_collision"],
                "provider_count_for_model_name": model["provider_count_for_model_name"],
                "disambiguated_name": model["disambiguated_name"],
                "metadata": {
                    "profile_source": "catalog",
                    "provider_model_key": model["qualified_model_id"],
                    "name_collision": model["name_collision"],
                    "provider_count_for_model_name": model["provider_count_for_model_name"],
                    "ambiguity_key": model["ambiguity_key"],
                },
            }
        )
    return profiles
