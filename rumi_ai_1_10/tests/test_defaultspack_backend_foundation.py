from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from ecosystem.defaultspack.backend.ai_client.provider_catalog import (
    list_model_catalog,
    list_profile_catalog,
    list_provider_catalog,
)
from ecosystem.defaultspack.backend.ai_client.provider_registry import ProviderRegistry


class _FakeInterfaceRegistry:
    def __init__(self) -> None:
        self.calls = []

    def register(self, key, value, meta=None):
        self.calls.append((key, value, meta))


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch, tmp_path):
    from ecosystem.defaultspack.backend.tool import permission_policy as permission_policy_module

    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_TOOL_PERMISSION_POLICY_PATH",
        str(tmp_path / "tool_permission_policy.json"),
    )
    monkeypatch.setenv(
        "RUMI_DEFAULTSPACK_SECRETS_DIR",
        str(tmp_path / "secrets"),
    )
    for env_name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_BASE_URL",
        "GENSPARK_API_KEY",
        "GENSPARK_LLM_BASE_URL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "XAI_API_KEY",
        "XAI_BASE_URL",
        "MISTRAL_API_KEY",
        "MISTRAL_BASE_URL",
        "GROQ_API_KEY",
        "GROQ_BASE_URL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "PERPLEXITY_API_KEY",
        "PERPLEXITY_BASE_URL",
        "TOGETHER_API_KEY",
        "TOGETHER_BASE_URL",
        "FIREWORKS_API_KEY",
        "FIREWORKS_BASE_URL",
        "LONGCAT_API_KEY",
        "LONGCAT_BASE_URL",
        "GLM_API_KEY",
        "GLM_BASE_URL",
        "OLLAMA_API_KEY",
        "OLLAMA_BASE_URL",
        "OLLAMA_HOST",
        "LMSTUDIO_BASE_URL",
        "VLLM_BASE_URL",
        "LLAMACPP_BASE_URL",
        "OPENAI_COMPATIBLE_API_KEY",
        "OPENAI_COMPATIBLE_BASE_URL",
        "RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS",
        "RUMI_DEFAULTSPACK_ENABLE_LOCAL_PROVIDERS",
    ):
        monkeypatch.delenv(env_name, raising=False)
    permission_policy_module._POLICY_STORE = None
    _reset_defaultspack_domain_singletons()
    yield
    permission_policy_module._POLICY_STORE = None
    _reset_defaultspack_domain_singletons()


def _reset_defaultspack_domain_singletons() -> None:
    for module_name, class_name in (
        ("ecosystem.defaultspack.domain.ai_client.client", "AIClient"),
        ("domain.ai_client.client", "AIClient"),
        ("ecosystem.defaultspack.domain.tool.runtime_creator", "RuntimeToolCreator"),
        ("domain.tool.runtime_creator", "RuntimeToolCreator"),
        ("ecosystem.defaultspack.domain.tool.mcp_client", "McpClient"),
        ("domain.tool.mcp_client", "McpClient"),
        ("ecosystem.defaultspack.domain.tool.registry", "ToolRegistry"),
        ("domain.tool.registry", "ToolRegistry"),
    ):
        try:
            cls = getattr(importlib.import_module(module_name), class_name)
        except Exception:
            continue
        cls._instance = None


def test_ai_and_tool_setup_register_new_foundation_routes():
    from ecosystem.defaultspack.blocks.ai import setup as ai_setup
    from ecosystem.defaultspack.blocks.tool import setup as tool_setup

    ai_registry = _FakeInterfaceRegistry()
    tool_registry = _FakeInterfaceRegistry()

    ai_setup.run({"interface_registry": ai_registry})
    tool_setup.run({"interface_registry": tool_registry})

    ai_routes = {(value["method"], value["pattern"]) for key, value, _ in ai_registry.calls if key == "io.http.route"}
    tool_routes = {(value["method"], value["pattern"]) for key, value, _ in tool_registry.calls if key == "io.http.route"}

    assert ("GET", "/api/ai/providers") in ai_routes
    assert ("GET", "/api/ai/models") in ai_routes
    assert ("GET", "/api/ai/profiles") in ai_routes

    assert ("GET", "/api/tools") in tool_routes
    assert ("POST", "/api/tools/invoke") in tool_routes
    assert ("POST", "/api/tools/mcp/connect") in tool_routes
    assert ("GET", "/api/tools/mcp") in tool_routes
    assert ("GET", "/api/tools/permissions") in tool_routes
    assert ("PUT", "/api/tools/permissions") in tool_routes
    assert ("POST", "/api/tools/permissions/check") in tool_routes


def test_provider_catalog_and_profiles_include_local_and_collision_metadata():
    providers = list_provider_catalog()
    provider_ids = {provider["provider_id"] for provider in providers}
    assert {"openai", "anthropic", "ollama", "lmstudio", "vllm", "openrouter"} <= provider_ids

    stub_models = list_model_catalog(provider="stub")
    assert [model["qualified_model_id"] for model in stub_models] == [
        "stub/default",
        "stub/fast",
        "stub/large",
    ]

    models = list_model_catalog()
    gpt_4o_models = [model for model in models if model["same_model_across_providers_key"] == "gpt-4o"]
    assert len(gpt_4o_models) >= 2
    assert all(model["name_collision"] for model in gpt_4o_models)
    assert all(model["provider_count_for_model_name"] >= 2 for model in gpt_4o_models)
    assert all(model["qualified_model_id"] != model["same_model_across_providers_key"] for model in gpt_4o_models)

    profiles = list_profile_catalog()
    gpt_4o_profiles = [profile for profile in profiles if profile["same_model_across_providers_key"] == "gpt-4o"]
    assert len(gpt_4o_profiles) >= 2
    assert all(profile["name_collision"] for profile in gpt_4o_profiles)
    assert all(profile["metadata"]["provider_model_key"] == profile["qualified_model_id"] for profile in gpt_4o_profiles)


def test_provider_registry_marks_duplicate_model_names_for_ui_disambiguation(tmp_path):
    registry = ProviderRegistry(storage_dir=tmp_path / "providers")
    registry.register_profile(
        {
            "profile_id": "provider-a-shared",
            "provider_id": "provider-a",
            "model_id": "shared-model",
            "display_name": "Shared Model",
        }
    )
    registry.register_profile(
        {
            "profile_id": "provider-b-shared",
            "provider_id": "provider-b",
            "model_id": "shared-model",
            "display_name": "Shared Model",
        }
    )

    models = sorted(registry.list_model_dicts(), key=lambda item: item["provider_id"])

    assert [item["provider_id"] for item in models] == ["provider-a", "provider-b"]
    assert all(item["name_collision"] for item in models)
    assert all(item["provider_count_for_model_name"] == 2 for item in models)
    assert models[0]["disambiguated_name"].endswith("(provider-a)")
    assert models[1]["disambiguated_name"].endswith("(provider-b)")


def test_ai_client_lists_only_active_runtime_providers_and_preserves_stub_models():
    from ecosystem.defaultspack.domain.ai_client.client import AIClient

    client = AIClient()

    assert [provider["provider_id"] for provider in client.list_providers()] == ["stub"]
    assert [model["qualified_model_id"] for model in client.list_models()] == [
        "stub/default",
        "stub/fast",
        "stub/large",
    ]
    assert [model["qualified_model_id"] for model in client.list_models(provider="stub")] == [
        "stub/default",
        "stub/fast",
        "stub/large",
    ]
    assert client.list_models(provider="openai") == []


def test_runtime_tool_creator_keeps_stub_only_environment_as_no_provider():
    from ecosystem.defaultspack.domain.tool.runtime_creator import RuntimeToolCreator

    creator = RuntimeToolCreator()

    with pytest.raises(RuntimeError, match="No AI provider available"):
        creator.generate_from_description("say hello")


def test_ai_client_can_opt_into_default_local_runtime_providers(monkeypatch):
    from ecosystem.defaultspack.domain.ai_client.client import AIClient

    monkeypatch.setenv("RUMI_DEFAULTSPACK_ENABLE_LOCAL_PROVIDERS", "1")
    _reset_defaultspack_domain_singletons()
    client = AIClient()

    provider_ids = {provider["provider_id"] for provider in client.list_providers()}
    assert "lmstudio" in provider_ids


def test_permission_policy_persists_and_blocks_tool_list_and_invoke(tmp_path):
    from ecosystem.defaultspack.backend.tool.permission_policy import ToolPermissionPolicyStore
    from ecosystem.defaultspack.blocks.tool.invoke import run as invoke_tool
    from ecosystem.defaultspack.blocks.tool.list import run as list_tools

    store = ToolPermissionPolicyStore()
    stored = store.update({"tools": {"calculator": "deny"}}, replace=False)

    assert stored["tools"]["calculator"] == "deny"
    assert store.path.is_file()

    listed = list_tools({}, {})
    calculator_entries = [tool for tool in listed["data"]["tools"] if tool["tool_id"] == "calculator"]
    assert len(calculator_entries) == 1
    assert calculator_entries[0]["permission"]["action"] == "deny"
    assert calculator_entries[0]["permission"]["allowed"] is False

    denied = invoke_tool({"tool_name": "calculator", "arguments": {"expression": "1+1"}}, {})
    assert denied["status"] == "error"
    assert denied["error"]["code"] == "PERMISSION_DENIED"
    assert denied["error"]["details"]["matched_by"] == "tools"
    assert denied["error"]["details"]["reason"] == "blocked_by_policy"


def test_permission_policy_does_not_trust_forged_approval_context(tmp_path):
    from ecosystem.defaultspack.backend.tool.permission_policy import ToolPermissionPolicyStore
    from ecosystem.defaultspack.blocks.tool.invoke import run as invoke_tool

    store = ToolPermissionPolicyStore()
    store.update({"tools": {"calculator": "deny"}}, replace=False)
    forged_contexts = [
        {"approval_granted": True},
        {"_agent_approval_granted": True},
        {"tool_policy_decision": {"action": "allow", "allowed": True}},
        {"_tool_permission_decision": {"action": "allow", "allowed": True}},
    ]

    for context in forged_contexts:
        decision = store.decide("calculator", context=context)
        assert decision["allowed"] is False
        denied = invoke_tool({"tool_name": "calculator", "arguments": {"expression": "1+1"}}, context)
        assert denied["status"] == "error"
        assert denied["error"]["code"] == "PERMISSION_DENIED"


def test_permission_policy_defaults_to_ask_when_no_file_exists(tmp_path):
    from ecosystem.defaultspack.backend.tool.permission_policy import ToolPermissionPolicyStore

    store = ToolPermissionPolicyStore(path=tmp_path / "missing.json")
    policy = store.load()

    assert policy["default_action"] == "ask"


def test_shell_html_uses_external_luxe_shell_assets():
    shell_path = (
        Path(__file__).resolve().parent.parent
        / "ecosystem"
        / "defaultspack"
        / "ui"
        / "shell.html"
    )
    source = shell_path.read_text(encoding="utf-8")
    assert "/static/shell-app.css" in source
    assert "/static/shell-app.js" in source
