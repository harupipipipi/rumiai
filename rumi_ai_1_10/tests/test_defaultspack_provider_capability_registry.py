from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_provider_capability_registry_loads_default_manifests():
    from domain.ai_client.capabilities.registry import default_registry

    registry = default_registry()
    assert {"openai", "google", "cerebras", "openrouter"}.issubset(set(registry.provider_ids()))


def test_provider_capability_registry_merges_model_metadata():
    from domain.ai_client.capabilities.registry import default_registry

    caps = default_registry().for_model(
        "openai/custom",
        {"provider_id": "openai", "capabilities": ["vision"], "max_context_tokens": 1234},
    )

    assert caps.supports_vision is True
    assert caps.max_context_tokens == 1234


def test_provider_capability_registry_cerebras_quirks_and_google_native():
    from domain.ai_client.capabilities.registry import default_registry

    cerebras = default_registry().for_model("cerebras/gpt-oss-120b")
    google = default_registry().for_model("google/gemma-4-31b-it")

    assert cerebras.quirks["max_tokens_name"] == "max_completion_tokens"
    assert google.api_family == "google_native"


def test_provider_capability_registry_uses_transport_metadata_for_anthropic_messages_models():
    from domain.ai_client.capabilities.registry import default_registry

    caps = default_registry().for_model(
        "opencode-zen/minimax-m3-free",
        {
            "provider_id": "opencode-zen",
            "capabilities": ["tool_calls", "vision", "reasoning"],
            "metadata": {"transport": "anthropic_messages"},
        },
    )

    assert caps.provider_id == "opencode-zen"
    assert caps.api_family == "anthropic_messages"
    assert caps.supports_tool_calling is True
    assert caps.supports_parallel_tool_calls is False
    assert "tool_call" in caps.supported_content_blocks
    assert caps.tool_choice_modes == ["auto", "none"]
    assert caps.quirks["tool_schema_subset"] == "input_schema"


def test_ai_client_runtime_model_includes_provider_capabilities():
    from domain.ai_client.client import AIClient
    from domain.ai_client.providers.stub_provider import StubProvider

    AIClient._instance = None
    client = AIClient()
    try:
        client.register_provider("custom", StubProvider())
        client._providers["custom"].KNOWN_MODELS = [{"id": "custom/model", "model_id": "model", "capabilities": ["vision"]}]
        models = client.list_models(provider="custom")
    finally:
        AIClient._instance = None

    model = next(item for item in models if item["id"] == "custom/model")
    assert "provider_capabilities" in model
    assert model["provider_capabilities"]["supports_vision"] is True
