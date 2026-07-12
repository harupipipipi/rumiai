from __future__ import annotations

import copy
import sys
from pathlib import Path

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.api.control_panel_handlers import ControlPanelHandlersMixin  # noqa: E402
from core_runtime.profile_runtime_selection import apply_profile_graph_selection  # noqa: E402
from core_runtime.profile_workspace import ProfileWorkspaceManager  # noqa: E402


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
            "metadata": {"selected": {"prompts": ["research.system"], "tools": ["web_search"]}},
            "policy": {},
        }
        self.profile_workspace_manager.initialize_profile_workspace(self.current_profile)

    def _build_catalog(self) -> dict:
        return {"packs": []}

    def _load_state(self, _catalog: dict) -> dict:
        return {"profiles": [copy.deepcopy(self.current_profile)], "active_profile_id": "research-profile"}

    def _get_profile(self, profiles: list[dict], profile_id: str) -> dict | None:
        for profile in profiles:
            if profile.get("profile_id") == profile_id:
                return copy.deepcopy(profile)
        return None

    def update_runtime_fields(self, profile_id: str, payload: dict) -> dict:
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
        return {"profile": copy.deepcopy(self.current_profile), "updated": True}


class _FakeToolRegistry:
    def list_tools(self):
        return [
            {"tool_id": "web_search", "name": "web_search", "schema": {"type": "object"}},
            {"tool_id": "computer_use", "name": "computer_use", "schema": {"type": "object"}},
        ]


def _fake_prompt(input_data):
    prompt_id = str(input_data.get("system_prompt_id") or "default_chat")
    return {
        "prompt_id": prompt_id,
        "source": f"test.{prompt_id}",
        "source_type": "profile_override",
        "content": f"Prompt text for {prompt_id}",
        "final_content": f"Prompt text for {prompt_id}",
        "source_chain": [],
    }


def _handler(monkeypatch, tmp_path: Path) -> tuple[_FakeHandler, _FakeManager]:
    monkeypatch.setattr("core_runtime.ai_input_segments.ToolRegistry", _FakeToolRegistry)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_prompt)
    manager = _FakeManager(tmp_path)
    handler = _FakeHandler()
    monkeypatch.setattr(handler, "_panel_startup_profile_manager", lambda: manager)
    return handler, manager


def test_ai_input_get_returns_effective_payload(monkeypatch, tmp_path: Path) -> None:
    handler, _manager = _handler(monkeypatch, tmp_path)

    payload = handler._panel_get_startup_profile_ai_input("research-profile", {"include_text": "false"})

    assert payload["profile_id"] == "research-profile"
    assert payload["graph"]["nodes"]
    assert payload["effective_input"]["system_segments"][0]["id"] == "prompt:research.system"
    assert "text" not in payload["effective_input"]["system_segments"][0]


def test_compile_preview_does_not_persist(monkeypatch, tmp_path: Path) -> None:
    handler, manager = _handler(monkeypatch, tmp_path)
    edge_id = "edge:prompt:research.system->model_input:default.system"

    preview = handler._panel_compile_startup_profile_ai_input_preview(
        "research-profile",
        {"ai_input": {"disabled_edges": [edge_id]}},
    )
    after = handler._panel_get_startup_profile_ai_input("research-profile", {"include_text": "false"})

    assert edge_id in preview["ai_input"]["disabled_edges"]
    assert manager.current_profile["metadata"].get("ai_input") is None
    assert after["ai_input"]["disabled_edges"] == []


def test_apply_persists_ai_input_config(monkeypatch, tmp_path: Path) -> None:
    handler, manager = _handler(monkeypatch, tmp_path)
    edge_id = "edge:prompt:research.system->model_input:default.system"

    payload = handler._panel_update_startup_profile_ai_input(
        "research-profile",
        {"ai_input": {"disabled_edges": [edge_id]}},
    )
    saved = manager.profile_workspace_manager.load_profile_yaml("research-profile")

    assert payload["ai_input"]["disabled_edges"] == [edge_id]
    assert manager.current_profile["metadata"]["ai_input"]["disabled_edges"] == [edge_id]
    assert saved["metadata"]["ai_input"]["disabled_edges"] == [edge_id]
