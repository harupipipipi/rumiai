from __future__ import annotations

import json
from pathlib import Path

import pytest

from ecosystem.defaultspack.domain.ai_client.providers import detect_available_providers
from ecosystem.defaultspack.domain.ai_client.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
)
from ecosystem.defaultspack.domain.ai_client.providers.openrouter_provider import (
    OpenRouterProvider,
)
from ecosystem.defaultspack.domain.extensions.discovery import discover_extensions
from ecosystem.defaultspack.domain.extensions.loading import import_entrypoint
from ecosystem.defaultspack.domain.extensions.manifest import (
    ManifestValidationError,
    validate_manifest,
)
from ecosystem.defaultspack.domain.extensions.registry import ExtensionRegistry
from ecosystem.defaultspack.domain.prompt.manager import PromptManager
from ecosystem.defaultspack.domain.tool.broker import ToolBroker
from ecosystem.defaultspack.domain.tool.registry import ToolRegistry
from ecosystem.defaultspack.transport.registry import build_fallback_http_routes
import ecosystem.defaultspack.domain.ai_client.providers as providers_module
import ecosystem.defaultspack.domain.prompt.manager as prompt_manager_module
import ecosystem.defaultspack.domain.tool.registry as tool_registry_module


class _DummyProvider:
    KNOWN_MODELS = [{"id": "dummy/m1", "name": "dummy-m1", "provider": "dummy", "type": "chat"}]


class _FakeLLMRegistry:
    def __init__(self, provider_manifests, model_manifests=None):
        self._provider_manifests = provider_manifests
        self._model_manifests = list(model_manifests or [])

    def providers(self, *, enabled_only: bool = True):
        if enabled_only:
            return [m for m in self._provider_manifests if bool(m.get("enabled", True))]
        return list(self._provider_manifests)

    def models(self, *, provider_id: str = "", enabled_only: bool = True):
        models = list(self._model_manifests)
        if enabled_only:
            models = [m for m in models if bool(m.get("enabled", True))]
        if provider_id:
            models = [m for m in models if m.get("provider_id") == provider_id]
        return models


class _FakeExtensionRegistry:
    def __init__(self, provider_manifests, model_manifests=None):
        self._llm = _FakeLLMRegistry(provider_manifests, model_manifests=model_manifests)

    def llm(self):
        return self._llm


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_manifest_validation_requires_provider_adapter_or_entrypoint():
    with pytest.raises(ManifestValidationError):
        validate_manifest(
            {
                "id": "x",
                "category": "llm_provider",
                "version": "1",
            },
            expected_category="llm_provider",
        )


def test_discovery_scans_manifest_categories(tmp_path: Path):
    root = tmp_path / "extensions"
    _write_json(
        root / "llm/providers/openai/manifest.json",
        {
            "id": "openai",
            "category": "llm_provider",
            "version": "1",
            "adapter": "openai_compatible",
            "enabled": True,
        },
    )
    _write_json(
        root / "llm/providers/openai/models/gpt-5.4.json",
        {
            "id": "openai/gpt-5.4",
            "category": "llm_model",
            "version": "1",
            "provider_id": "openai",
            "model_id": "gpt-5.4",
            "priority": 10,
            "defaults": {"chat": True},
        },
    )
    _write_json(
        root / "prompts/base_assistant/manifest.json",
        {
            "id": "base_assistant",
            "category": "prompt",
            "version": "1",
        },
    )

    result = discover_extensions(root)
    assert len(result.issues) == 0
    assert {(item.category, item.extension_id) for item in result.extensions} >= {
        ("llm_provider", "openai"),
        ("llm_model", "openai/gpt-5.4"),
        ("prompt", "base_assistant"),
    }


def test_extension_registry_llm_best_model(tmp_path: Path):
    root = tmp_path / "extensions"
    _write_json(
        root / "llm/providers/openai/manifest.json",
        {
            "id": "openai",
            "category": "llm_provider",
            "version": "1",
            "adapter": "openai_compatible",
            "enabled": True,
        },
    )
    _write_json(
        root / "llm/providers/openai/models/gpt-5-mini.json",
        {
            "id": "openai/gpt-5-mini",
            "category": "llm_model",
            "version": "1",
            "provider_id": "openai",
            "model_id": "gpt-5-mini",
            "priority": 50,
            "defaults": {"chat": True},
        },
    )
    _write_json(
        root / "llm/providers/openai/models/gpt-5.4.json",
        {
            "id": "openai/gpt-5.4",
            "category": "llm_model",
            "version": "1",
            "provider_id": "openai",
            "model_id": "gpt-5.4",
            "priority": 10,
            "defaults": {"chat": True},
        },
    )

    registry = ExtensionRegistry(root)
    best = registry.llm().best_model("openai", use_case="chat")
    assert best is not None
    assert best["model_id"] == "gpt-5.4"


def test_extension_registry_synthesizes_provider_default_models(tmp_path: Path):
    root = tmp_path / "extensions"
    _write_json(
        root / "llm/providers/openrouter/manifest.json",
        {
            "id": "openrouter",
            "category": "llm_provider",
            "version": "1",
            "entrypoint": f"{__name__}:_DummyProvider",
            "default_model": "auto",
            "default_model_for": {"chat": "auto", "fast": "openai/gpt-5.4-mini"},
            "enabled": True,
        },
    )

    registry = ExtensionRegistry(root)
    chat_default = registry.llm().best_model("openrouter", use_case="chat")
    fast_default = registry.llm().best_model("openrouter", use_case="fast")
    assert chat_default is not None
    assert chat_default["model_id"] == "auto"
    assert fast_default is not None
    assert fast_default["model_id"] == "openai/gpt-5.4-mini"


def test_extension_registry_preserves_google_api_key_env_list():
    root = (
        Path(__file__).resolve().parent.parent
        / "ecosystem"
        / "rumi_model_catalog_pack"
        / "extensions"
    )

    registry = ExtensionRegistry(root)
    google = next(
        provider
        for provider in registry.llm().providers(enabled_only=True)
        if provider["id"] == "google"
    )

    assert google["api_key_env"] == ["GOOGLE_API_KEY", "GEMINI_API_KEY"]


def test_extension_registry_lists_rumi_bundle_ui_surface():
    root = (
        Path(__file__).resolve().parent.parent
        / "ecosystem"
        / "defaultspack"
        / "extensions"
    )

    registry = ExtensionRegistry(root)
    surfaces = {item["id"]: item for item in registry.ui_surfaces().list(enabled_only=True)}
    assert "rumi_bundle" in surfaces
    assert surfaces["rumi_bundle"]["config"]["module_id"] == "rumi_bundle"
    assert surfaces["rumi_bundle"]["config"]["launch_mode"] == "desktop_app"
    assert surfaces["rumi_bundle"]["config"]["port_source"]["default"] == 8766


def test_openrouter_provider_lists_only_hy3_preview_free(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-token")

    provider = OpenRouterProvider()
    models = provider.list_models()
    assert [model["id"] for model in models] == ["openrouter/tencent/hy3-preview:free"]
    assert models[0]["model_id"] == "tencent/hy3-preview:free"


def test_openrouter_provider_rejects_non_allowlisted_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-token")

    provider = OpenRouterProvider()
    with pytest.raises(RuntimeError, match="tencent/hy3-preview:free"):
        provider.complete("openai/gpt-4o-mini", [{"role": "user", "content": "hi"}], [], {})


def test_detect_available_providers_uses_manifest_registry(monkeypatch):
    entrypoint = f"{__name__}:_DummyProvider"
    provider_manifests = [
        {
            "id": "generic_openai_like",
            "category": "llm_provider",
            "version": "1",
            "adapter": "openai_compatible",
            "enabled": True,
            "credential_required": False,
            "default_base_url": "https://example.test/v1",
        },
        {
            "id": "dummy",
            "category": "llm_provider",
            "version": "1",
            "entrypoint": entrypoint,
            "enabled": True,
            "credential_required": False,
        },
    ]
    fake_registry = _FakeExtensionRegistry(provider_manifests)
    monkeypatch.setattr(
        providers_module,
        "get_extension_registry",
        lambda force_reload=True: fake_registry,
    )
    monkeypatch.setattr(providers_module, "_load_legacy_providers", lambda: {})

    available = detect_available_providers()
    assert isinstance(available["generic_openai_like"], OpenAICompatibleProvider)
    assert isinstance(available["dummy"], _DummyProvider)


def test_openai_compatible_provider_uses_model_manifests():
    manifest = {
        "id": "generic_openai_like",
        "category": "llm_provider",
        "version": "1",
        "adapter": "openai_compatible",
        "default_base_url": "https://example.test/v1",
        "credential_required": False,
    }
    model_manifests = [
        {
            "provider_id": "generic_openai_like",
            "model_id": "latest-model",
            "display_name": "Latest Model",
            "type": "chat",
            "defaults": {"chat": True},
        }
    ]
    provider = OpenAICompatibleProvider.from_manifest(
        manifest,
        model_manifests=model_manifests,
    )
    models = provider.list_models()
    assert len(models) == 1
    assert models[0]["id"] == "generic_openai_like/latest-model"
    assert models[0]["model_id"] == "latest-model"
    assert models[0]["provider"] == "generic_openai_like"
    assert models[0]["provider_id"] == "generic_openai_like"
    assert models[0]["name"] == "Latest Model"
    assert models[0]["defaults"] == {"chat": True}


def test_prompt_manager_lists_extension_prompts(monkeypatch, tmp_path: Path):
    extensions_root = tmp_path / "extensions"
    _write_json(
        extensions_root / "prompts/default_chat/manifest.json",
        {
            "id": "default_chat",
            "category": "prompt",
            "version": "1",
            "enabled": True,
            "config": {"template_file": "prompt.md"},
        },
    )
    (extensions_root / "prompts/default_chat/prompt.md").write_text(
        "hello {{name}}\n",
        encoding="utf-8",
    )

    registry = ExtensionRegistry(extensions_root)
    monkeypatch.setattr(prompt_manager_module, "get_extension_registry", lambda force_reload=True: registry)
    monkeypatch.setattr(prompt_manager_module, "get_extensions_root", lambda: extensions_root)

    manager = PromptManager()
    prompt = manager.get_prompt_by_name("default_chat")
    assert prompt is not None
    assert prompt["metadata"]["source"] == "extension"
    assert "hello {{name}}" in prompt["body"]


def test_tool_registry_loads_extension_tools(monkeypatch, tmp_path: Path):
    extensions_root = tmp_path / "extensions"
    _write_json(
        extensions_root / "tools/calculator/manifest.json",
        {
                "id": "custom_calc",
            "category": "tool",
            "version": "1",
            "enabled": True,
            "config": {
                "name": "custom_calc",
                "summary": "計算",
                "tags": ["math"],
                "schema": {
                    "parameters": {
                        "type": "object",
                        "properties": {"expression": {"type": "string"}},
                        "required": ["expression"],
                    }
                },
                "execution": {"type": "local"},
            },
        },
    )

    registry = ExtensionRegistry(extensions_root)
    monkeypatch.setattr(tool_registry_module, "get_extension_registry", lambda force_reload=True: registry)
    ToolRegistry._instance = None
    tool_registry = ToolRegistry()
    tool = tool_registry.get("custom_calc")
    assert tool is not None
    assert tool["metadata"]["source"] == "extension"
    assert tool["summary"] == "計算"


def test_tool_broker_prefers_native_strategy_when_capability_present():
    broker = ToolBroker()
    strategy = broker.select_strategy(
        {"capabilities": {"native_tool_calling": True}},
        [{"name": "calculator"}],
    )
    assert strategy == "native"
    prepared = broker.prepare_provider_tools(
        {"capabilities": {"native_tool_calling": False}},
        [{"name": "calculator"}],
    )
    assert prepared["strategy"] == "prompt_fallback"
    assert prepared["tool_names"] == ["calculator"]


def test_import_entrypoint_normalizes_legacy_module_names():
    loaded = import_entrypoint("domain.ai_client.providers.openai_compatible_provider:OpenAICompatibleProvider")
    assert loaded is OpenAICompatibleProvider


def test_build_fallback_http_routes_contains_core_routes():
    class _Server:
        def _invoke_fallback_block(self, block_module, request_data, path_params, inject=None):
            return {
                "block_module": block_module,
                "inject": inject or {},
                "path_params": path_params,
            }

        def _handle_health(self, request_data, path_params):
            return {"status": "ok"}

        def _handle_context_info(self, request_data, path_params):
            return {"status": "ok"}

        def _handle_chat_redirect(self, request_data, path_params):
            return {"status": "ok"}

        def _handle_static(self, request_data, path_params):
            return {"status": "ok"}

        def _handle_static_file(self, request_data, path_params):
            return {"status": "ok"}

    routes = build_fallback_http_routes(_Server())
    route_methods = {(method, compiled.pattern) for method, compiled, _, _, _ in routes}
    assert ("POST", "^/v1/chat/completions$") in route_methods
    assert ("GET", "^/api/health$") in route_methods
