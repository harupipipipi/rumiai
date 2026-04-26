from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set


def tool_name_from_definition(tool: Any) -> str:
    if isinstance(tool, str):
        return tool
    if not isinstance(tool, dict):
        return ""
    function_def = tool.get("function")
    if isinstance(function_def, dict) and function_def.get("name"):
        return str(function_def.get("name"))
    return str(tool.get("name") or tool.get("tool_id") or "")


def adapt_tool_definition(tool: Any) -> Any:
    """Normalize defaultspack tool records to provider function-tool shape."""
    if not isinstance(tool, dict):
        return tool
    if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
        return tool

    name = tool_name_from_definition(tool)
    if not name:
        return tool
    schema = tool.get("schema") if isinstance(tool.get("schema"), dict) else {}
    parameters = schema.get("parameters") if isinstance(schema.get("parameters"), dict) else schema
    if not isinstance(parameters, dict) or not parameters:
        parameters = {"type": "object", "properties": {}, "required": []}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": str(tool.get("summary") or tool.get("description") or ""),
            "parameters": parameters,
        },
    }


def adapt_tool_definitions(tools: Iterable[Any]) -> List[Any]:
    return [adapt_tool_definition(tool) for tool in tools]


def filter_tool_definitions_for_runtime_profile(
    tools: Iterable[Any],
    runtime_profile: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
) -> List[Any]:
    normalized = list(tools)
    enforced = runtime_profile_enforced_tool_names(
        runtime_profile,
        agent_id,
        normalized,
    )
    if enforced is None:
        return normalized
    return [
        tool
        for tool in normalized
        if tool_name_from_definition(tool) in enforced
    ]


def connected_tool_names(
    tools: Iterable[Any],
    runtime_profile: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
) -> Set[str]:
    names = {name for name in (tool_name_from_definition(tool) for tool in tools) if name}
    names.update(_runtime_profile_tool_names(runtime_profile, agent_id, tools))
    return names


def runtime_profile_enforced_tool_names(
    runtime_profile: Optional[Dict[str, Any]],
    agent_id: Optional[str] = None,
    tools: Optional[Iterable[Any]] = None,
) -> Optional[Set[str]]:
    if not runtime_profile:
        return None
    return _runtime_profile_tool_names(runtime_profile, agent_id, tools)


def build_tool_execution_context(
    base_context: Dict[str, Any],
    tool_name: str,
    connected_tools: Iterable[str],
) -> Dict[str, Any]:
    context = dict(base_context or {})
    graph_id = context.get("graph_id") or context.get("capability_graph_id")
    profile_id = context.get("profile_id") or context.get("capability_profile_id")
    principal_id = context.get("principal_id") or context.get("principal")
    context["capability_graph"] = {
        "graph_id": graph_id,
        "profile_id": profile_id,
        "principal_id": principal_id,
        "tool_name": tool_name,
        "connected_tools": sorted(str(name) for name in connected_tools if name),
    }
    return context


def max_tool_calls(context: Dict[str, Any]) -> Optional[int]:
    policy = context.get("profile_policy")
    if not isinstance(policy, dict):
        runtime_profile = context.get("runtime_profile")
        if isinstance(runtime_profile, dict):
            policy = runtime_profile.get("policy")
    if not isinstance(policy, dict):
        return None
    value = policy.get("max_tool_calls")
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _runtime_profile_tool_names(
    runtime_profile: Optional[Dict[str, Any]],
    agent_id: Optional[str],
    tools: Optional[Iterable[Any]] = None,
) -> Set[str]:
    refs = _runtime_profile_tool_refs(runtime_profile, agent_id)
    if not refs:
        return set()

    supplied_names = {
        name for name in (tool_name_from_definition(tool) for tool in (tools or [])) if name
    }
    defaultspack = runtime_profile.get("defaultspack") if isinstance(runtime_profile, dict) else None
    bundles = defaultspack.get("tools") if isinstance(defaultspack, dict) else None
    bundles = bundles if isinstance(bundles, dict) else {}

    names: Set[str] = set()
    for ref in refs:
        if ref in supplied_names:
            names.add(ref)
            continue
        bundle_record = bundles.get(ref)
        if isinstance(bundle_record, dict):
            bundle_names = _tool_names_from_bundle_record(bundle_record)
            if bundle_names:
                names.update(bundle_names)
            else:
                names.update(supplied_names)
            continue
        names.add(ref)
    return names


def _runtime_profile_tool_refs(
    runtime_profile: Optional[Dict[str, Any]],
    agent_id: Optional[str],
) -> Set[str]:
    if not isinstance(runtime_profile, dict):
        return set()
    defaultspack = runtime_profile.get("defaultspack")
    if not isinstance(defaultspack, dict):
        return set()
    agents = defaultspack.get("agents")
    if not isinstance(agents, dict):
        return set()
    selected = agents.get(agent_id) if agent_id else None
    if not isinstance(selected, dict) and len(agents) == 1:
        selected = next(iter(agents.values()))
    if not isinstance(selected, dict):
        return set()
    tools = selected.get("tools", [])
    if not isinstance(tools, list):
        return set()
    return {str(tool) for tool in tools if tool}


def _tool_names_from_bundle_record(record: Dict[str, Any]) -> Set[str]:
    names: Set[str] = set()
    for key in ("tools", "tool_ids", "tool_names", "definitions"):
        values = record.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            name = tool_name_from_definition(value)
            if name:
                names.add(name)
    return names
