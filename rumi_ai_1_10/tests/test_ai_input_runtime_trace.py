from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.profile_runtime_selection import apply_profile_graph_selection  # noqa: E402
from core_runtime.profile_workspace import ProfileWorkspaceManager  # noqa: E402
from domain.chat.run_request import prepare_chat_run  # noqa: E402
from domain.chat.store import ChatStore  # noqa: E402


class _Decision:
    def __init__(self, model: str) -> None:
        self.selected_model = model
        self.original_model = model
        self.selected_group = "default"
        self.reason_codes = ["test"]
        self.warnings = []
        self.bridge_required = False
        self.bridge_plan = {}

    def to_dict(self) -> dict:
        return {"selected_model": self.selected_model}


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
        "content": f"Runtime prompt for {prompt_id}",
        "final_content": f"Runtime prompt for {prompt_id}",
        "source_chain": [],
    }


def test_ai_input_trace_is_applied_to_chat_runtime_context(monkeypatch, tmp_path: Path) -> None:
    user_data_root = tmp_path / "user_data"
    chat_store_path = tmp_path / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_USER_DATA", str(user_data_root))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(chat_store_path))
    ChatStore._instance = None

    profile = {
        "profile_id": "research-profile",
        "name": "Research Profile",
        "base_pack": "defaultspack",
        "metadata": {"selected": {"prompts": ["research.system"], "tools": ["web_search"]}},
        "policy": {},
    }
    manager = ProfileWorkspaceManager(user_data_root)
    manager.initialize_profile_workspace(profile)
    manager.save_profile_yaml(profile["profile_id"], apply_profile_graph_selection(profile))
    active_marker = user_data_root / "profiles" / "active_profile.json"
    active_marker.parent.mkdir(parents=True, exist_ok=True)
    active_marker.write_text(
        json.dumps({"version": 1, "active_profile_id": profile["profile_id"]}) + "\n",
        encoding="utf-8",
    )

    conversation = ChatStore().create_conversation(model="stub/default")
    monkeypatch.setattr("core_runtime.ai_input_segments.ToolRegistry", _FakeToolRegistry)
    monkeypatch.setattr("core_runtime.ai_input_segments.resolve_effective_prompt", _fake_prompt)
    monkeypatch.setattr("domain.chat.run_request.route_model_request", lambda request: _Decision("stub/default"))
    monkeypatch.setattr(
        "domain.chat.run_request.get_model_capabilities",
        lambda model: {
            "supports_image_input": False,
            "supports_vision": False,
            "supports_tool_calling": True,
            "supports_thinking": True,
        },
    )
    monkeypatch.setattr(
        "domain.chat.run_request.RuntimeSkillTriggerService",
        lambda: type("SkillTrigger", (), {"evaluate": lambda self, **kwargs: {"matched": [], "instructions": ""}})(),
    )
    monkeypatch.setattr(
        "domain.chat.run_request._resolve_selected_tools",
        lambda raw_tools, **kwargs: (
            [
                {"tool_id": "web_search", "name": "web_search", "schema": {"parameters": {"type": "object"}}},
                {"tool_id": "computer_use", "name": "computer_use", "schema": {"parameters": {"type": "object"}}},
            ],
            [],
        ),
    )

    prepared = prepare_chat_run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "search the web"},
        },
        {},
    )

    assert prepared.request_context["ai_input_trace"]["profile_id"] == "research-profile"
    assert prepared.request_context["effective_tool_allowlist"] == ["web_search"]
    assert "Runtime prompt for research.system" in prepared.standard_messages[0]["content"]
    trace_dir = user_data_root / "profiles" / "research-profile" / "runtime_traces"
    trace = json.loads((trace_dir / "latest_ai_input.json").read_text(encoding="utf-8"))
    assert trace["blocked"] == []
    ChatStore._instance = None
