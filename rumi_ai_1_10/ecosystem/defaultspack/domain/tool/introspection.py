from __future__ import annotations

from typing import Any

from .permission_checker import PermissionChecker
from .registry import ToolRegistry
from .schema_adapter import (
    filter_tool_definitions_for_runtime_profile,
    resolve_runtime_profile_context,
)


def _tool_name(tool: dict[str, Any]) -> str:
    return str(tool.get("tool_id") or tool.get("name") or "").strip()


def _permission_scoped_tools(
    tools: list[dict[str, Any]],
    *,
    registry: ToolRegistry,
    context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    resolved_context = resolve_runtime_profile_context(context or {})
    runtime_profile = resolved_context.get("runtime_profile")
    scoped = filter_tool_definitions_for_runtime_profile(
        tools,
        runtime_profile if isinstance(runtime_profile, dict) else None,
        agent_id=resolved_context.get("agent_id"),
        policy_context=resolved_context,
    )
    checker = PermissionChecker(registry=registry)
    visible: list[dict[str, Any]] = []
    for tool in scoped:
        name = _tool_name(tool)
        if not name:
            continue
        decision = checker.decide(name, context=resolved_context, tool_def=tool)
        if str(decision.get("action") or "").strip().lower() == "deny":
            continue
        visible.append(tool)
    return visible


def current_tool_names(
    args: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = args if isinstance(args, dict) else {}
    filter_dict = data.get("filter") if isinstance(data.get("filter"), dict) else None
    registry = ToolRegistry()
    tools = registry.list_tools(filter_dict=filter_dict)
    names = []
    for tool in _permission_scoped_tools(tools, registry=registry, context=context):
        name = _tool_name(tool)
        if name:
            names.append(name)
    names = sorted(dict.fromkeys(names))
    return {"names": names, "tool_names": names, "count": len(names)}


def tool_names(args: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return current_tool_names(args, context)
