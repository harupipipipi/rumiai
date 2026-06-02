from __future__ import annotations

from typing import Any

from domain.tool.schema_adapter import tool_name_from_definition


def _as_record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _compact_required(value: Any) -> dict[str, Any]:
    required = _as_record(value)
    compact: dict[str, Any] = {}
    for key in ("model_capabilities", "input_modalities", "runtime_capabilities"):
        items = _string_list(required.get(key))
        if items:
            compact[key] = items
    attachment_policy = str(required.get("attachment_policy") or "").strip()
    if attachment_policy:
        compact["attachment_policy"] = attachment_policy
    supports_attachments = required.get("supports_attachments")
    if supports_attachments is not None:
        compact["supports_attachments"] = supports_attachments
    capability_requirements = _as_record(required.get("capability_requirements"))
    if any(capability_requirements.get(key) for key in ("requires_all", "requires_any", "forbids")):
        compact["capability_requirements"] = capability_requirements
    return compact


def compact_tool_filter_entries(entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    compact_entries: list[dict[str, Any]] = []
    for entry_value in entries:
        entry = _as_record(entry_value)
        tool_name = str(entry.get("tool_name") or "").strip()
        if not tool_name:
            continue
        compact: dict[str, Any] = {
            "tool_name": tool_name,
            "status": str(entry.get("status") or "blocked").strip() or "blocked",
        }
        for key in ("reason_code", "reason"):
            value = str(entry.get(key) or "").strip()
            if value:
                compact[key] = value
        required = _compact_required(entry.get("required"))
        if required:
            compact["required"] = required
        repair_suggestions = _string_list(entry.get("repair_suggestions"))[:2]
        if repair_suggestions:
            compact["repair_suggestions"] = repair_suggestions
        compact_entries.append(compact)
    return compact_entries


def _compact_provider_tool(tool: Any) -> dict[str, Any]:
    tool_record = _as_record(tool)
    function = _as_record(tool_record.get("function"))
    name = tool_name_from_definition(tool_record)
    compact: dict[str, Any] = {}
    if name:
        compact["name"] = name
    tool_type = str(tool_record.get("type") or "").strip()
    if tool_type:
        compact["type"] = tool_type
    description = str(function.get("description") or tool_record.get("description") or "").strip()
    if description:
        compact["description"] = description[:240]
    return compact


def _compact_provider_context(context: Any) -> dict[str, Any]:
    context_record = _as_record(context)
    compact: dict[str, Any] = {}
    for key in ("conversation_id", "request_id", "run_source", "phase", "model"):
        value = context_record.get(key)
        if value not in (None, ""):
            compact[key] = value
    tool_filter_result = context_record.get("tool_filter_result")
    if isinstance(tool_filter_result, list):
        compact["tool_filter_count"] = len(tool_filter_result)
    runtime_snapshot = _as_record(context_record.get("runtime_capability_snapshot"))
    if runtime_snapshot:
        compact["runtime_capability_snapshot"] = runtime_snapshot
    return compact


def compact_provider_planning(planning: Any) -> dict[str, Any]:
    planning_record = _as_record(planning)
    if not planning_record:
        return {}
    compact: dict[str, Any] = {}
    for key in ("model", "params", "bridge_actions", "dropped_features", "warnings", "provider_capabilities"):
        value = planning_record.get(key)
        if value not in (None, "", [], {}):
            compact[key] = value
    provider_tools = planning_record.get("provider_tools")
    if isinstance(provider_tools, list):
        compact["provider_tool_count"] = len(provider_tools)
        compact_tools = []
        for tool in provider_tools:
            compact_tool = _compact_provider_tool(tool)
            if compact_tool:
                compact_tools.append(compact_tool)
        compact["provider_tools"] = compact_tools
    metadata = _as_record(planning_record.get("metadata"))
    if metadata:
        compact_metadata = {
            key: value
            for key, value in metadata.items()
            if key not in {"context", "provider_tool_definitions", "tool_name_mapping"}
        }
        context = _compact_provider_context(metadata.get("context"))
        if context:
            compact_metadata["context"] = context
        provider_tool_definitions = metadata.get("provider_tool_definitions")
        if isinstance(provider_tool_definitions, list):
            compact_metadata["provider_tool_definition_count"] = len(provider_tool_definitions)
        tool_name_mapping = metadata.get("tool_name_mapping")
        if isinstance(tool_name_mapping, dict):
            compact_metadata["tool_name_mapping_count"] = len(tool_name_mapping)
        if compact_metadata:
            compact["metadata"] = compact_metadata
    return compact


def compact_message_metadata(metadata: Any) -> Any:
    if not isinstance(metadata, dict):
        return metadata
    compact = dict(metadata)
    if "tool_filter_result" in compact:
        compact["tool_filter_result"] = compact_tool_filter_entries(compact.get("tool_filter_result"))
    if "provider_planning" in compact:
        compact["provider_planning"] = compact_provider_planning(compact.get("provider_planning"))
    return compact


def compact_conversation_for_response(conversation: dict[str, Any]) -> dict[str, Any]:
    compact_conversation = dict(conversation)
    messages = compact_conversation.get("messages")
    if not isinstance(messages, list):
        return compact_conversation
    compact_messages: list[dict[str, Any]] = []
    for message_value in messages:
        if not isinstance(message_value, dict):
            compact_messages.append(message_value)
            continue
        message = dict(message_value)
        message["metadata"] = compact_message_metadata(message.get("metadata"))
        compact_messages.append(message)
    compact_conversation["messages"] = compact_messages
    return compact_conversation
