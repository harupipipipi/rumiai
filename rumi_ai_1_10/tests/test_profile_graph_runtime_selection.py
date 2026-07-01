from __future__ import annotations

import sys
from pathlib import Path

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from core_runtime.profile_runtime_selection import apply_profile_graph_selection  # noqa: E402
from core_runtime.startup_capability_bridge import _apply_startup_runtime_selection  # noqa: E402
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


def test_multiple_selected_tools_survive_startup_selection_and_runtime_policy_filter() -> None:
    startup_profile = {
        "profile_id": "research-profile",
        "metadata": {
            "selected": {
                "tools": ["web_search", "computer_use"],
            }
        },
        "policy": {
            "tool_allowlist": ["computer_use", "web_search"],
            "max_tool_calls": 2,
        },
    }
    runtime_profile = _apply_startup_runtime_selection(
        {
            "policy": {
                "tool_allowlist": ["legacy_tool"],
                "allow_shell": False,
            },
            "defaultspack": {
                "agents": {
                    "assistant": {
                        "tools": ["web_search", "computer_use", "terminal_exec"],
                    },
                    "researcher": {
                        "tools": ["file_read", "web_search", "computer_use"],
                    },
                    "bundle_agent": {
                        "tools": ["tools"],
                    },
                    "planner": {},
                }
            },
        },
        startup_profile,
    )

    filtered = filter_tool_definitions_for_runtime_profile(
        adapt_tool_definitions(
            [
                {"name": "web_search", "metadata": {"action_type": "read"}, "schema": {}},
                {"name": "computer_use", "metadata": {"action_type": "read"}, "schema": {}},
                {"name": "terminal_exec", "metadata": {"action_type": "shell"}, "schema": {}},
                {"name": "file_read", "metadata": {"action_type": "read"}, "schema": {}},
            ]
        ),
        runtime_profile,
        agent_id="assistant",
    )

    assert runtime_profile["policy"]["tool_allowlist"] == ["computer_use", "web_search"]
    assert runtime_profile["policy"]["max_tool_calls"] == 2
    assert runtime_profile["policy"]["allow_shell"] is False
    assert runtime_profile["defaultspack"]["agents"]["assistant"]["tools"] == ["web_search", "computer_use"]
    assert runtime_profile["defaultspack"]["agents"]["researcher"]["tools"] == ["web_search", "computer_use"]
    assert runtime_profile["defaultspack"]["agents"]["bundle_agent"]["tools"] == ["web_search", "computer_use"]
    assert runtime_profile["defaultspack"]["agents"]["planner"]["tools"] == ["web_search", "computer_use"]
    assert [tool["function"]["name"] for tool in filtered] == ["web_search", "computer_use"]


def test_profile_graph_selected_tools_are_applied_to_runtime_context() -> None:
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

    normalized = apply_profile_graph_selection(profile)
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
        normalized,
    )

    filtered = filter_tool_definitions_for_runtime_profile(
        adapt_tool_definitions(
            [
                {"name": "web_search", "metadata": {"action_type": "read"}, "schema": {}},
                {"name": "computer_use", "metadata": {"action_type": "read"}, "schema": {}},
            ]
        ),
        runtime_profile,
        agent_id="assistant",
    )

    assert normalized["system_prompt_id"] == "research.system"
    assert runtime_profile["policy"]["tool_allowlist"] == ["web_search"]
    assert runtime_profile["defaultspack"]["agents"]["assistant"]["tools"] == ["web_search"]
    assert [tool["function"]["name"] for tool in filtered] == ["web_search"]
