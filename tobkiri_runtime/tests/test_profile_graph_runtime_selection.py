from __future__ import annotations

import sys
import json
from pathlib import Path
from typing import Any

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.profile_workspace import ProfileWorkspaceManager  # noqa: E402
from core_runtime.profile_runtime_selection import apply_profile_graph_selection  # noqa: E402
from core_runtime.startup_capability_bridge import _apply_startup_runtime_selection  # noqa: E402
from domain.chat.run_request import prepare_chat_run  # noqa: E402
from domain.chat.store import ChatStore  # noqa: E402
from ecosystem.rumi_conversation_store_pack.runtime.store import ConversationStore  # noqa: E402
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


def test_apply_profile_graph_selection_syncs_prompt_changes() -> None:
    profile = {
        "profile_id": "research-profile",
        "system_prompt_id": "research.system",
        "metadata": {
            "selected": {
                "tools": [],
                "webhooks": [],
                "api_routes": [],
                "prompts": ["coding.system"],
                "frontend": [],
                "flows": [],
                "nodes": [],
            }
        },
    }

    normalized = apply_profile_graph_selection(profile)

    assert normalized["system_prompt_id"] == "coding.system"


def test_apply_profile_graph_selection_projects_launch_surface_node_override() -> None:
    profile = {
        "profile_id": "research-profile",
        "node_overrides": {"frontend.surface": "defaultspack.frontend_surface"},
        "metadata": {
            "selected": {
                "tools": [],
                "webhooks": [],
                "api_routes": [],
                "prompts": [],
                "frontend": [],
                "flows": [],
                "nodes": ["test_profile_frontend_pack.web_surface"],
            },
            "profile_graph": {
                "nodes": [
                    {
                        "id": "node:test_profile_frontend_pack.web_surface",
                        "kind": "capability_node",
                        "ref": "test_profile_frontend_pack.web_surface",
                        "metadata": {
                            "component_type": "frontend",
                            "launch": {"kind": "desktop_app", "pack_id": "test_profile_frontend_pack"},
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
        },
    }

    normalized = apply_profile_graph_selection(profile)

    assert normalized["node_overrides"]["frontend.surface"] == "test_profile_frontend_pack.web_surface"


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
    from domain.chat import store as chat_store_facade

    owner = ConversationStore("default", user_data_root=user_data_root)

    def invoke_owner(contract_id: str, operation: str, payload: dict[str, Any]) -> Any:
        if contract_id == chat_store_facade.CONVERSATION:
            if operation == "list":
                return owner.snapshot()
            if operation == "get":
                return owner.get(str(payload.get("conversation_id") or ""))
        if contract_id == chat_store_facade.MESSAGE and operation == "get":
            conversation = owner.get(str(payload.get("conversation_id") or ""))
            return next(
                (
                    message
                    for message in (conversation or {}).get("messages", [])
                    if message.get("id") == payload.get("message_id")
                ),
                None,
            )
        if contract_id == chat_store_facade.CONVERSATION_MANAGE:
            if operation == "create":
                return owner.create(
                    payload["conversation"],
                    expected_revision=int(payload["expected_revision"]),
                )
            if operation == "update":
                return owner.update(
                    str(payload["conversation_id"]),
                    payload["patch"],
                    expected_conversation_revision=int(
                        payload["expected_conversation_revision"]
                    ),
                )
            if operation == "delete":
                return owner.delete(
                    str(payload["conversation_id"]),
                    expected_conversation_revision=int(
                        payload["expected_conversation_revision"]
                    ),
                )
        if contract_id == chat_store_facade.MESSAGE_MANAGE:
            if operation == "append":
                return owner.append_message(
                    str(payload["conversation_id"]),
                    payload["message"],
                    expected_conversation_revision=int(
                        payload["expected_conversation_revision"]
                    ),
                )
            if operation == "update":
                return owner.mutate_message(
                    str(payload["conversation_id"]),
                    str(payload["message_id"]),
                    patch=payload.get("patch") or {},
                    expected_conversation_revision=int(
                        payload["expected_conversation_revision"]
                    ),
                )
            if operation == "delete":
                return owner.mutate_message(
                    str(payload["conversation_id"]),
                    str(payload["message_id"]),
                    delete=True,
                    expected_conversation_revision=int(
                        payload["expected_conversation_revision"]
                    ),
                )
        raise AssertionError(f"unexpected contract call: {contract_id}/{operation}")

    # ChatStore is a compatibility facade; bind it to the canonical owner for
    # this integration test instead of relying on a process-global owner.
    monkeypatch.setattr(chat_store_facade, "_invoke", invoke_owner)

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
    fake_tools = [
        {
            "tool_id": "web_search",
            "name": "web_search",
            "summary": "Search",
            "schema": {
                "parameters": {
                    "type": "object",
                    "properties": {},
                }
            },
            "metadata": {"action_type": "read"},
        },
        {
            "tool_id": "computer_use",
            "name": "computer_use",
            "summary": "Operate the computer",
            "schema": {
                "parameters": {
                    "type": "object",
                    "properties": {},
                }
            },
            "metadata": {"action_type": "read"},
        },
    ]
    # The chat path now reads the canonical finite tool catalog and compiles
    # selected definitions through Capability Plan. Supply that catalog in
    # the fixture instead of bypassing the path with the retired resolver.
    from domain.chat import run_request as run_request_module

    monkeypatch.setattr(
        run_request_module.ToolRegistry,
        "list_tools",
        lambda self: list(fake_tools),
    )
    monkeypatch.setattr(
        run_request_module.ToolRegistry,
        "get",
        lambda self, tool_name: next(
            (tool for tool in fake_tools if tool["tool_id"] == tool_name),
            None,
        ),
    )

    prepared = prepare_chat_run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "search the web"},
            "params": {
                "tool_selection": {
                    "mode": "manual",
                    "include": ["web_search", "computer_use"],
                }
            },
        },
        {"developer_mode": True},
    )

    assert prepared.request_context["profile_policy"]["tool_allowlist"] == ["web_search"]
    assert prepared.request_context["active_startup_profile_id"] == "research-profile"
    assert prepared.conversation["system_prompt_id"] == "research.system"
    assert [tool["function"]["name"] for tool in prepared.provider_tools] == ["web_search", "assistant_progress"]
    ChatStore._instance = None
