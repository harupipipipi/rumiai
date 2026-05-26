from __future__ import annotations

import sys
import json
from pathlib import Path

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.profile_workspace import ProfileWorkspaceManager  # noqa: E402
from core_runtime.profile_runtime_selection import apply_profile_graph_selection  # noqa: E402
from core_runtime.startup_capability_bridge import _apply_startup_runtime_selection  # noqa: E402
from domain.chat.run_request import prepare_chat_run  # noqa: E402
from domain.chat.store import ChatStore  # noqa: E402
from domain.tool.schema_adapter import adapt_tool_definitions, filter_tool_definitions_for_runtime_profile  # noqa: E402


def test_apply_profile_graph_selection_projects_selected_fields() -> None:
    profile = {
        "profile_id": "research-profile",
        "metadata": {
            "selected": {
                "tools": ["web_search"],
                "api_routes": ["POST /api/chat/conversations/{id}/messages"],
                "prompts": ["research.system"],
            }
        },
        "policy": {"max_tool_calls": 3},
    }

    normalized = apply_profile_graph_selection(profile)

    assert normalized["policy"]["max_tool_calls"] == 3
    assert normalized["policy"]["tool_allowlist"] == ["web_search"]
    assert normalized["policy"]["api_route_allowlist"] == ["POST /api/chat/conversations/{id}/messages"]
    assert normalized["system_prompt_id"] == "research.system"


def test_unselected_tools_are_rejected_by_runtime_policy_filter() -> None:
    startup_profile = {
        "profile_id": "research-profile",
        "metadata": {
            "selected": {
                "tools": ["web_search"],
            }
        },
    }
    runtime_profile = _apply_startup_runtime_selection(
        {
            "defaultspack": {
                "agents": {
                    "assistant": {
                        "tools": ["web_search", "computer_use"],
                    }
                }
            }
        },
        startup_profile,
    )

    filtered = filter_tool_definitions_for_runtime_profile(
        adapt_tool_definitions(
            [
                {"name": "web_search", "metadata": {"action_type": "read"}, "schema": {}},
                {"name": "computer_use", "metadata": {"action_type": "read"}, "schema": {}},
            ]
        ),
        runtime_profile,
    )

    assert runtime_profile["policy"]["tool_allowlist"] == ["web_search"]
    assert runtime_profile["defaultspack"]["agents"]["assistant"]["tools"] == ["web_search"]
    assert [tool["function"]["name"] for tool in filtered] == ["web_search"]


def test_profile_graph_selected_tools_are_applied_to_chat_runtime_context(monkeypatch, tmp_path: Path) -> None:
    user_data_root = tmp_path / "user_data"
    chat_store_path = tmp_path / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_USER_DATA", str(user_data_root))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(chat_store_path))
    ChatStore._instance = None

    profile = {
        "profile_id": "research-profile",
        "name": "Research Profile",
        "base_pack": "defaultspack",
        "system_prompt_id": "research.system",
        "metadata": {
            "selected": {
                "tools": ["web_search"],
            }
        },
        "policy": {},
    }
    manager = ProfileWorkspaceManager(user_data_root)
    manager.initialize_profile_workspace(profile)
    manager.save_profile_yaml(profile["profile_id"], apply_profile_graph_selection(profile))
    active_marker = user_data_root / "profiles" / "active_profile.json"
    active_marker.parent.mkdir(parents=True, exist_ok=True)
    active_marker.write_text(
        json.dumps({"version": 1, "active_profile_id": profile["profile_id"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    conversation = ChatStore().create_conversation(model="stub/default")

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
                {"tool_id": "web_search", "name": "web_search", "summary": "Search", "schema": {"parameters": {"type": "object", "properties": {}}}},
                {"tool_id": "computer_use", "name": "computer_use", "summary": "Operate the computer", "schema": {"parameters": {"type": "object", "properties": {}}}},
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

    assert prepared.request_context["profile_policy"]["tool_allowlist"] == ["web_search"]
    assert prepared.request_context["active_startup_profile_id"] == "research-profile"
    assert prepared.conversation["system_prompt_id"] == "research.system"
    assert [tool["function"]["name"] for tool in prepared.provider_tools] == ["web_search"]
    ChatStore._instance = None
