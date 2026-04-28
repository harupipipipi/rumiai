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
    adapted = {
        "type": "function",
        "function": {
            "name": name,
            "description": str(tool.get("summary") or tool.get("description") or ""),
            "parameters": parameters,
        },
    }
    for key in ("metadata", "category", "action_type", "write_action"):
        if key in tool:
            adapted[key] = tool[key]
    return adapted


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
    policy = _policy_from_runtime_profile(runtime_profile)
    if enforced is None:
        return [
            tool for tool in normalized
            if not is_tool_rejected_by_policy(tool, policy)
        ]
    filtered = [
        tool
        for tool in normalized
        if tool_name_from_definition(tool) in enforced
    ]
    return [
        tool for tool in filtered
        if not is_tool_rejected_by_policy(tool, policy)
    ]


def resolve_runtime_profile_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve runtime_profile_key into runtime_profile when possible."""
    resolved = dict(context or {})
    if isinstance(resolved.get("capability_profile"), dict):
        resolved.setdefault("runtime_profile", resolved["capability_profile"])
        return resolved
    if isinstance(resolved.get("runtime_profile"), dict):
        return resolved
    key = resolved.get("runtime_profile_key") or resolved.get("_runtime_profile_key")
    registry = resolved.get("interface_registry")
    if isinstance(key, str) and key and registry is not None:
        getter = getattr(registry, "get", None)
        if callable(getter):
            profile = getter(key)
            if isinstance(profile, dict):
                resolved["runtime_profile"] = profile
                resolved["_runtime_profile_key"] = key
                return resolved
    try:
        from core_runtime.runtime_profile_resolver import resolve_runtime_profile_context as core_resolve

        return core_resolve(resolved, interface_registry=registry)
    except Exception:
        return resolved


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


def is_tool_rejected_by_policy(tool: Any, policy: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(policy, dict):
        return False
    category = _tool_metadata_value(tool, "category")
    action_type = _tool_metadata_value(tool, "action_type")
    if policy.get("allow_shell") is False and (category == "shell" or action_type == "shell"):
        return True
    if policy.get("allow_file_write") is False and (
        category in {"file_write", "filesystem_write"}
        or action_type in {"write", "file_write", "delete", "create", "update"}
    ):
        return True
    return False


def tool_requires_approval_by_policy(tool: Any, policy: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(policy, dict) or policy.get("write_actions_require_approval") is not True:
        return False
    return _tool_metadata_value(tool, "write_action") is True or _tool_metadata_value(tool, "action_type") in {
        "write",
        "file_write",
        "delete",
        "create",
        "update",
    }


def policy_from_context(context: Dict[str, Any]) -> Dict[str, Any]:
    policy = context.get("profile_policy")
    if isinstance(policy, dict):
        return policy
    runtime_profile = context.get("runtime_profile")
    return _policy_from_runtime_profile(runtime_profile)


def _policy_from_runtime_profile(runtime_profile: Any) -> Dict[str, Any]:
    if isinstance(runtime_profile, dict) and isinstance(runtime_profile.get("policy"), dict):
        return dict(runtime_profile["policy"])
    return {}


def _tool_metadata_value(tool: Any, key: str) -> Any:
    if not isinstance(tool, dict):
        return None
    if key in tool:
        return tool.get(key)
    metadata = tool.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(key)
    execution = tool.get("execution")
    if isinstance(execution, dict):
        return execution.get(key)
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
            elif not _bundle_record_has_concrete_tool_list(bundle_record):
                names.update(supplied_names)
            continue
        names.add(ref)
    return names


def _bundle_record_has_concrete_tool_list(record: Dict[str, Any]) -> bool:
    return any(isinstance(record.get(key), list) for key in ("tools", "tool_ids", "tool_names", "definitions"))


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
