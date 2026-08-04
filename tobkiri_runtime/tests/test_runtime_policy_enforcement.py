from __future__ import annotations

import sys
from pathlib import Path

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.tool.executor import ToolExecutor  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402
from domain.tool.schema_adapter import (  # noqa: E402
    adapt_tool_definitions,
    filter_tool_definitions_for_runtime_profile,
    resolve_runtime_profile_context,
)
from core_runtime.interface_registry import InterfaceRegistry  # noqa: E402


def test_runtime_profile_key_resolves_from_interface_registry() -> None:
    registry = InterfaceRegistry()
    runtime_profile = {"policy": {"max_tool_calls": 2}, "registry_key": "runtime_profile.sample"}
    registry.register("runtime_profile.sample", runtime_profile)

    context = resolve_runtime_profile_context(
        {"runtime_profile_key": "runtime_profile.sample", "interface_registry": registry}
    )

    assert context["runtime_profile"] == runtime_profile
    assert context["_runtime_profile_key"] == "runtime_profile.sample"


def test_policy_filters_shell_and_file_write_tools_from_provider_tools() -> None:
    tools = [
        {"name": "search", "metadata": {"action_type": "read"}, "schema": {}},
        {"name": "run_shell", "metadata": {"category": "shell"}, "schema": {}},
        {"name": "write_file", "metadata": {"action_type": "file_write"}, "schema": {}},
    ]
    runtime_profile = {
        "policy": {"allow_shell": False, "allow_file_write": False},
        "defaultspack": {"agents": {"agent": {"tools": ["search", "run_shell", "write_file"]}}},
    }

    filtered = filter_tool_definitions_for_runtime_profile(adapt_tool_definitions(tools), runtime_profile)

    names = [tool["function"]["name"] for tool in filtered]
    assert names == ["search"]


def test_policy_filters_tool_allowlist_and_denylist() -> None:
    tools = [
        {"name": "rumi_api", "metadata": {"action_type": "read"}, "schema": {}},
        {"name": "web_search", "metadata": {"action_type": "read"}, "schema": {}},
        {"name": "coding_terminal_exec", "metadata": {"category": "shell"}, "schema": {}},
    ]
    runtime_profile = {
        "policy": {
            "tool_allowlist": ["rumi_api", "web_search", "coding_terminal_exec"],
            "tool_denylist": ["web_search"],
            "allow_shell": False,
        },
        "defaultspack": {"agents": {"agent": {"tools": ["rumi_api", "web_search", "coding_terminal_exec"]}}},
    }

    filtered = filter_tool_definitions_for_runtime_profile(adapt_tool_definitions(tools), runtime_profile)

    assert [tool["function"]["name"] for tool in filtered] == ["rumi_api"]


def test_tool_executor_rejects_policy_blocked_tool(
    defaultspack_capability_plan_context,
) -> None:
    ToolRegistry._instance = None
    registry = ToolRegistry()
    registry.register(
        {
            "tool_id": "write_file",
            "name": "write_file",
            "schema": {"parameters": {"type": "object", "properties": {}, "required": []}},
            "execution": {"type": "local", "action_type": "file_write"},
        }
    )
    plan_context = defaultspack_capability_plan_context("write_file")

    result = ToolExecutor().execute(
        "write_file",
        {},
        {**plan_context, "profile_policy": {"allow_file_write": False}},
    )

    assert result["is_error"] is True
    assert result["rejected_by_policy"] is True
