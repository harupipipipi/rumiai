from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.api.control_panel_handlers import ControlPanelHandlersMixin
from core_runtime.profile_graph_builder import (
    _startup_catalog_nodes,
    build_startup_profile_graph_response,
)
from core_runtime.profile_graph_models import normalize_profile_graph_document
from core_runtime.profile_runtime_selection import apply_profile_graph_selection
from core_runtime.profile_workspace import ProfileWorkspaceManager
from core_runtime.startup_profiles import StartupProfileManager
from ecosystem.defaultspack.transport.registry import HttpRouteSpec


class _FakeHandler(ControlPanelHandlersMixin):
    kernel = None
    app_lifecycle_manager = None


class _FakeManager:
    def __init__(self, tmp_path: Path) -> None:
        self.profile_workspace_manager = ProfileWorkspaceManager(tmp_path / "user_data")
        self.ecosystem_dir = str(tmp_path / "ecosystem")
        self.current_profile = {
            "version": 3,
            "profile_id": "research-profile",
            "name": "Research Profile",
            "base_pack": "defaultspack",
            "graph_id": "defaultspack.startup",
            "graph_ports": [],
            "packs": ["defaultspack"],
            "node_overrides": {},
            "created_at": 1,
            "updated_at": 1,
            "metadata": {},
            "policy": {},
        }
        self.profile_workspace_manager.initialize_profile_workspace(self.current_profile)

    def _build_catalog(self) -> dict:
        return {"packs": []}

    def _load_state(self, _catalog: dict) -> dict:
        return {
            "profiles": [copy.deepcopy(self.current_profile)],
            "active_profile_id": self.current_profile["profile_id"],
            "last_launched_profile_id": None,
        }

    def _get_profile(self, profiles: list[dict], profile_id: str) -> dict | None:
        for profile in profiles:
            if profile.get("profile_id") == profile_id:
                return copy.deepcopy(profile)
        return None

    def update_profile(self, profile_id: str, payload: dict) -> dict:
        assert profile_id == self.current_profile["profile_id"]
        merged = copy.deepcopy(self.current_profile)
        for key, value in payload.items():
            if key in {"metadata", "policy"} and isinstance(value, dict):
                current = merged.get(key) if isinstance(merged.get(key), dict) else {}
                merged[key] = {**current, **value}
            else:
                merged[key] = value
        self.current_profile = apply_profile_graph_selection(merged)
        self.profile_workspace_manager.save_profile_yaml(profile_id, self.current_profile)
        return {"profile": copy.deepcopy(self.current_profile)}

    def update_runtime_fields(self, profile_id: str, payload: dict) -> dict:
        return self.update_profile(profile_id, payload)

    def compile_profile_preview(self, profile_id: str, payload: dict | None = None) -> dict:
        preview_profile = payload.get("profile") if isinstance(payload, dict) else None
        merged = copy.deepcopy(self.current_profile)
        if isinstance(preview_profile, dict):
            for key, value in preview_profile.items():
                if key in {"metadata", "policy"} and isinstance(value, dict):
                    current = merged.get(key) if isinstance(merged.get(key), dict) else {}
                    merged[key] = {**current, **value}
                else:
                    merged[key] = value
        normalized = apply_profile_graph_selection(merged)
        return {
            "ok": True,
            "profile_id": profile_id,
            "profile": normalized,
            "capability_graph": {"ok": True, "diagnostics": []},
            "diagnostics": [],
        }


def _graph_response(profile: dict, **_kwargs) -> dict:
    metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
    document, _ = normalize_profile_graph_document(
        profile["profile_id"],
        metadata.get("profile_graph"),
        metadata.get("selected"),
    )
    return {
        "profile_id": profile["profile_id"],
        "profile": copy.deepcopy(profile),
        "graph": document.to_dict(),
        "available": {
            "tools": [{"id": "web_search", "label": "Web Search", "kind": "tool"}],
            "webhooks": [{"id": "research-webhook", "label": "Research Webhook", "kind": "webhook"}],
            "api_routes": [{"id": "POST /api/chat/conversations/{id}/messages", "label": "POST /api/chat/conversations/{id}/messages", "kind": "api"}],
            "prompts": [{"id": "research.system", "label": "Research Prompt", "kind": "prompt"}],
            "frontend": [{"id": "research_sidebar", "label": "Research Sidebar", "kind": "frontend"}],
            "flows": [{"id": "research.flow", "label": "Research Flow", "kind": "flow"}],
            "capability_nodes": [{"id": "research.node", "label": "Research Node", "kind": "capability_node"}],
        },
        "summary": {
            "selected_tool_count": len(document.selected.get("tools") or []),
            "available_tool_count": 1,
            "selected_webhook_count": len(document.selected.get("webhooks") or []),
            "available_webhook_count": 1,
            "api_route_count": 1,
            "selected_frontend_count": len(document.selected.get("frontend") or []),
            "selected_prompt_count": len(document.selected.get("prompts") or []),
        },
        "diagnostics": [],
    }


def _setup_builder_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ProfileWorkspaceManager:
    ecosystem_root = tmp_path / "ecosystem"
    defaultspack_root = ecosystem_root / "defaultspack"
    flows_dir = defaultspack_root / "flows"
    prompts_dir = defaultspack_root / "prompts"
    defaultspack_root.mkdir(parents=True, exist_ok=True)
    (defaultspack_root / "ecosystem.json").write_text(json.dumps({"pack_id": "defaultspack"}), encoding="utf-8")
    flows_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (flows_dir / "research.flow.yaml").write_text("flow_id: research.flow\nname: Research Flow\n", encoding="utf-8")
    (prompts_dir / "research.system.md").write_text("# Research Prompt\n", encoding="utf-8")

    workspace_manager = ProfileWorkspaceManager(tmp_path / "workspace")
    profile = {
        "profile_id": "research-profile",
        "name": "Research Profile",
        "base_pack": "defaultspack",
        "graph_id": "defaultspack.startup",
        "metadata": {},
        "policy": {},
    }
    paths = workspace_manager.initialize_profile_workspace(profile)
    (paths.prompts_dir / "research.system.md").write_text("workspace prompt\n", encoding="utf-8")

    class _FakeToolRegistry:
        def list_tools(self):
            return [
                {
                    "tool_id": "web_search",
                    "name": "web_search",
                    "display_name": "Web Search",
                    "execution": {"handler": "domain.search:web_search"},
                    "metadata": {"manifest_path": str(tmp_path / "tool.json")},
                }
            ]

    class _FakeWebhookEndpointStore:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_endpoints(self):
            return [
                {
                    "id": "research-webhook",
                    "kind": "generic",
                    "input_profile_id": "ingress.research",
                    "default_delivery": {"action_id": "deliver.research"},
                    "enabled": True,
                }
            ]

    class _FakeInputProfileRegistry:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_profiles(self):
            return [SimpleNamespace(id="ingress.research", display_name="Ingress Research", provider="web")]

    class _FakeFrontendRegistry:
        def __init__(self, *_args, **_kwargs):
            pass

        def build_catalog(self, profile_id=None):
            return {
                "sidebar": {
                    "items": [
                        {
                            "id": "research_sidebar",
                            "label": "Research Sidebar",
                            "profile_visibility": {"selected_frontend_ids": ["research_sidebar"]},
                        }
                    ]
                }
            }

    class _FakeCapabilityCatalog:
        def __init__(self, *_args, **_kwargs):
            pass

        def prompts(self):
            return [{"id": "research.system", "name": "Research Prompt", "content_ref": "prompts/research.system.md"}]

    monkeypatch.setattr("core_runtime.profile_graph_builder.ToolRegistry", _FakeToolRegistry)
    monkeypatch.setattr("core_runtime.profile_graph_builder.WebhookEndpointStore", _FakeWebhookEndpointStore)
    monkeypatch.setattr("core_runtime.profile_graph_builder.InputProfileRegistry", _FakeInputProfileRegistry)
    monkeypatch.setattr("core_runtime.profile_graph_builder.FrontendRegistry", _FakeFrontendRegistry)
    monkeypatch.setattr("core_runtime.profile_graph_builder.CapabilityCatalog", _FakeCapabilityCatalog)
    monkeypatch.setattr(
        "core_runtime.profile_graph_builder.canonical_http_route_specs",
        lambda include_always_available=True: [
            HttpRouteSpec(
                method="POST",
                pattern="/api/chat/conversations/{id}/messages",
                block_module="chat.messages",
                function_name="post_messages",
                flow_id="research.flow",
                fallback_block_module="chat.fallback",
                handler_name="post_messages",
            )
        ],
    )
    return workspace_manager


def test_profile_graph_get_includes_available_tools_webhooks_api_prompts_frontend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_manager = _setup_builder_catalog(monkeypatch, tmp_path)
    profile = {
        "profile_id": "research-profile",
        "name": "Research Profile",
        "base_pack": "defaultspack",
        "graph_id": "defaultspack.startup",
        "metadata": {},
        "policy": {},
    }

    payload = build_startup_profile_graph_response(
        profile,
        startup_catalog={
            "packs": [
                {
                    "pack_id": "defaultspack",
                    "nodes": [{"node_id": "research.node", "display_name": {"en": "Research Node"}}],
                }
            ]
        },
        profile_workspace_manager=workspace_manager,
        ecosystem_dir=str(tmp_path / "ecosystem"),
    )

    assert payload["available"]["tools"][0]["id"] == "web_search"
    assert payload["available"]["webhooks"][0]["id"] == "research-webhook"
    assert payload["available"]["api_routes"][0]["id"] == "POST /api/chat/conversations/{id}/messages"
    assert "research.system" in [item["id"] for item in payload["available"]["prompts"]]
    assert payload["available"]["frontend"][0]["id"] == "research_sidebar"


def test_profile_graph_projects_only_selected_pack_contract_candidates(
    tmp_path: Path,
) -> None:
    class _ApprovedPacks:
        @staticmethod
        def get_approval(_pack_id: str) -> object:
            return object()

        @staticmethod
        def is_pack_approved_and_verified(
            _pack_id: str,
        ) -> tuple[bool, str]:
            return True, "verified fixture"

    ecosystem = tmp_path / "ecosystem"
    selected_pack = ecosystem / "rumi_file_inspect_pack"
    unrelated_pack = ecosystem / "unrelated_pack"
    selected_pack.mkdir(parents=True)
    unrelated_pack.mkdir()
    (selected_pack / "ecosystem.json").write_text(
        json.dumps({"pack_id": "rumi_file_inspect_pack"}),
        encoding="utf-8",
    )
    (selected_pack / "rumi.pack.v3.json").write_text(
        json.dumps(
            {
                "contracts": {
                    "provides": [
                        {
                            "id": "rumi.service.file.inspect.v1",
                            "provider_instance_id": "file-inspect.service",
                            "required_capabilities": ["file.inspect"],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (unrelated_pack / "ecosystem.json").write_text(
        json.dumps({"pack_id": "unrelated_pack"}),
        encoding="utf-8",
    )
    manager = StartupProfileManager(
        storage_path=tmp_path / "startup_profiles.json",
        ecosystem_dir=str(ecosystem),
        approval_manager=_ApprovedPacks(),
        seed_default_profile=False,
    )
    catalog = manager._build_catalog()

    candidates = _startup_catalog_nodes(
        catalog,
        {
            "base_pack": "defaultspack",
            "packs": ["defaultspack", "rumi_file_inspect_pack"],
        },
    )

    inspect_candidate = next(
        item
        for item in candidates
        if item["source_pack_id"] == "rumi_file_inspect_pack"
        and item["metadata"].get("contract_id")
    )
    assert inspect_candidate["id"] == (
        "rumi_file_inspect_pack.contract.file-inspect.service"
    )
    assert inspect_candidate["metadata"]["contract_id"] == (
        "rumi.service.file.inspect.v1"
    )
    assert not any(
        item["source_pack_id"] == "unrelated_pack" for item in candidates
    )


def test_profile_graph_update_persists_metadata_selected_and_projects_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager = _FakeManager(tmp_path)
    monkeypatch.setattr("core_runtime.profile_graph_builder.build_startup_profile_graph_response", _graph_response)
    handler = _FakeHandler()
    monkeypatch.setattr(handler, "_panel_startup_profile_manager", lambda: manager)

    result = handler._panel_update_startup_profile_graph(
        "research-profile",
        {
            "graph": {
                "nodes": [{"id": "profile:research-profile", "kind": "profile"}],
                "edges": [],
            },
            "selected": {
                "tools": ["web_search"],
                "prompts": ["research.system"],
                "api_routes": ["POST /api/chat/conversations/{id}/messages"],
                "frontend": ["research_sidebar"],
            },
        },
    )

    selected = result["profile"]["metadata"]["selected"]
    assert selected["tools"] == ["web_search"]
    assert result["profile"]["policy"]["tool_allowlist"] == ["web_search"]
    assert result["profile"]["policy"]["api_route_allowlist"] == ["POST /api/chat/conversations/{id}/messages"]
    assert result["profile"]["system_prompt_id"] == "research.system"
    assert result["graph"]["selected"]["frontend"] == ["research_sidebar"]


def test_profile_graph_update_clears_system_prompt_when_prompt_selection_is_removed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager = _FakeManager(tmp_path)
    manager.current_profile["system_prompt_id"] = "research.system"
    manager.current_profile["metadata"] = {
        "selected": {
            "tools": [],
            "webhooks": [],
            "api_routes": [],
            "prompts": ["research.system"],
            "frontend": [],
            "flows": [],
            "nodes": [],
        }
    }
    monkeypatch.setattr("core_runtime.profile_graph_builder.build_startup_profile_graph_response", _graph_response)
    handler = _FakeHandler()
    monkeypatch.setattr(handler, "_panel_startup_profile_manager", lambda: manager)

    result = handler._panel_update_startup_profile_graph(
        "research-profile",
        {
            "graph": {
                "nodes": [{"id": "profile:research-profile", "kind": "profile"}],
                "edges": [],
            },
            "selected": {
                "tools": [],
                "prompts": [],
            },
        },
    )

    assert result["profile"]["system_prompt_id"] is None
    assert result["profile"]["metadata"]["selected"]["prompts"] == []


def test_profile_graph_compile_preview_returns_runtime_selection_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager = _FakeManager(tmp_path)
    monkeypatch.setattr("core_runtime.profile_graph_builder.build_startup_profile_graph_response", _graph_response)
    handler = _FakeHandler()
    monkeypatch.setattr(handler, "_panel_startup_profile_manager", lambda: manager)

    result = handler._panel_compile_startup_profile_graph_preview(
        "research-profile",
        {
            "graph": {
                "nodes": [{"id": "profile:research-profile", "kind": "profile"}],
                "edges": [],
            },
            "selected": {
                "tools": ["web_search"],
                "api_routes": ["POST /api/chat/conversations/{id}/messages"],
                "webhooks": ["research-webhook"],
            },
        },
    )

    runtime_preview = result["profile_graph_runtime_preview"]
    assert runtime_preview["selected"]["tools"] == ["web_search"]
    assert runtime_preview["policy"]["tool_allowlist"] == ["web_search"]
    assert runtime_preview["webhook_runtime"]["selected"] == ["research-webhook"]
    assert runtime_preview["webhook_runtime"]["effective"][0]["profile_selection_applied"] is True
    assert "does not disable unselected endpoints" in runtime_preview["webhook_runtime"]["warning"]
    assert any(
        diagnostic.get("code") == "api_route_allowlist_not_enforced"
        for diagnostic in runtime_preview["diagnostics"]
    )


def test_profile_graph_compile_preview_uses_saved_selection_when_body_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager = _FakeManager(tmp_path)
    manager.current_profile["metadata"] = {
        "profile_graph": {
            "nodes": [
                {
                    "id": "node:test_profile_frontend_pack.web_surface",
                    "kind": "node",
                    "ref": "test_profile_frontend_pack.web_surface",
                    "metadata": {
                        "component_type": "frontend",
                        "launch": {
                            "kind": "desktop_app",
                            "pack_id": "test_profile_frontend_pack",
                            "surface": "browser",
                            "default": True,
                        },
                        "ports": [
                            {
                                "id": "surface",
                                "direction": "output",
                                "standards": ["rumi.surface"],
                            }
                        ],
                    },
                }
            ],
            "edges": [],
        },
        "selected": {
            "tools": ["web_search"],
            "webhooks": [],
            "api_routes": [],
            "prompts": [],
            "frontend": [],
            "flows": [],
            "nodes": ["test_profile_frontend_pack.web_surface"],
        }
    }
    manager.current_profile["policy"] = {"tool_allowlist": ["web_search"]}
    manager.current_profile["node_overrides"] = {
        "frontend.surface": "test_profile_frontend_pack.web_surface",
    }
    monkeypatch.setattr("core_runtime.profile_graph_builder.build_startup_profile_graph_response", _graph_response)
    handler = _FakeHandler()
    monkeypatch.setattr(handler, "_panel_startup_profile_manager", lambda: manager)

    result = handler._panel_compile_startup_profile_graph_preview("research-profile", {})

    runtime_preview = result["profile_graph_runtime_preview"]
    assert runtime_preview["selected"]["tools"] == ["web_search"]
    assert result["compile_preview"]["profile"]["node_overrides"]["frontend.surface"] == "test_profile_frontend_pack.web_surface"
