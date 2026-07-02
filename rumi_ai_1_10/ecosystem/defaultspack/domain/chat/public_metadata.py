from __future__ import annotations

from typing import Any

from domain.tool.schema_adapter import tool_name_from_definition

DEFAULT_CONVERSATION_MESSAGE_LIMIT = 120
MAX_CONVERSATION_MESSAGE_LIMIT = 500
DEFAULT_MESSAGE_TEXT_LIMIT = 2000
MAX_MESSAGE_TEXT_LIMIT = 24000
_AUX_TEXT_LIMIT = 1000
_AUX_LIST_LIMIT = 30
_AUX_DICT_LIMIT = 80
_METADATA_TEXT_LIMIT = 160
_METADATA_LIST_LIMIT = 3
_METADATA_DICT_LIMIT = 12
_EVENT_LIST_LIMIT = 4
_EVENT_TEXT_LIMIT = 180
_EVENT_DICT_LIMIT = 16
_TOOL_LOG_LIST_LIMIT = 3
_TOOL_LOG_TEXT_LIMIT = 220
_TOOL_LOG_DICT_LIMIT = 20


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


def _clip_text(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    omitted = len(value) - max(0, limit)
    if limit <= 0:
        return f"[truncated {omitted} chars]", True
    return value[:limit].rstrip() + f"\n[truncated {omitted} chars]", True


def _compact_aux_value(
    value: Any,
    *,
    depth: int = 0,
    text_limit: int = _AUX_TEXT_LIMIT,
    list_limit: int = _AUX_LIST_LIMIT,
    dict_limit: int = _AUX_DICT_LIMIT,
) -> tuple[Any, bool]:
    if depth > 4:
        return "[truncated depth]", True
    if isinstance(value, str):
        return _clip_text(value, text_limit)
    if isinstance(value, list):
        truncated = len(value) > list_limit
        items = value[-list_limit:]
        compact_items = []
        for item in items:
            compact_item, item_truncated = _compact_aux_value(
                item,
                depth=depth + 1,
                text_limit=text_limit,
                list_limit=list_limit,
                dict_limit=dict_limit,
            )
            truncated = truncated or item_truncated
            compact_items.append(compact_item)
        return compact_items, truncated
    if isinstance(value, dict):
        truncated = len(value) > dict_limit
        compact: dict[str, Any] = {}
        for index, key in enumerate(value):
            if index >= dict_limit:
                break
            compact_value, value_truncated = _compact_aux_value(
                value[key],
                depth=depth + 1,
                text_limit=text_limit,
                list_limit=list_limit,
                dict_limit=dict_limit,
            )
            truncated = truncated or value_truncated
            compact[str(key)] = compact_value
        return compact, truncated
    return value, False


def _compact_content(content: Any, text_limit: int) -> tuple[Any, bool]:
    if isinstance(content, str):
        return _clip_text(content, text_limit)
    if not isinstance(content, list):
        return content, False
    remaining = max(0, text_limit)
    truncated = False
    compact_blocks: list[Any] = []
    for block_value in content:
        if isinstance(block_value, dict):
            block = dict(block_value)
            text = block.get("text")
            if isinstance(text, str):
                if remaining <= 0:
                    block["text"] = "[truncated]"
                    truncated = True
                else:
                    clipped, was_truncated = _clip_text(text, remaining)
                    block["text"] = clipped
                    truncated = truncated or was_truncated
                    remaining = max(0, remaining - len(clipped))
            compact_blocks.append(block)
        elif isinstance(block_value, str):
            if remaining <= 0:
                compact_blocks.append("[truncated]")
                truncated = True
            else:
                clipped, was_truncated = _clip_text(block_value, remaining)
                compact_blocks.append(clipped)
                truncated = truncated or was_truncated
                remaining = max(0, remaining - len(clipped))
        else:
            compact_blocks.append(block_value)
    return compact_blocks, truncated


def compact_message_for_response(
    message_value: Any,
    *,
    text_limit: int = DEFAULT_MESSAGE_TEXT_LIMIT,
) -> Any:
    if not isinstance(message_value, dict):
        return message_value
    message = dict(message_value)
    truncated_fields: set[str] = set()
    normalized_limit = max(0, min(MAX_MESSAGE_TEXT_LIMIT, int(text_limit)))

    if "content" in message:
        compact_content, truncated = _compact_content(message.get("content"), normalized_limit)
        message["content"] = compact_content
        if truncated:
            truncated_fields.add("content")
    if isinstance(message.get("raw_text"), str):
        clipped, truncated = _clip_text(str(message.get("raw_text") or ""), normalized_limit)
        message["raw_text"] = clipped
        if truncated:
            truncated_fields.add("raw_text")

    metadata = compact_message_metadata(message.get("metadata"))
    metadata, metadata_truncated = _compact_aux_value(
        metadata,
        text_limit=_METADATA_TEXT_LIMIT,
        list_limit=_METADATA_LIST_LIMIT,
        dict_limit=_METADATA_DICT_LIMIT,
    )
    if metadata_truncated:
        truncated_fields.add("metadata")
    message["metadata"] = metadata

    for field, item_limit, text_limit, dict_limit in (
        ("events", _EVENT_LIST_LIMIT, _EVENT_TEXT_LIMIT, _EVENT_DICT_LIMIT),
        ("tool_logs", _TOOL_LOG_LIST_LIMIT, _TOOL_LOG_TEXT_LIMIT, _TOOL_LOG_DICT_LIMIT),
    ):
        value = message.get(field)
        if isinstance(value, list):
            truncated = len(value) > item_limit
            compact_value, value_truncated = _compact_aux_value(
                value[-item_limit:],
                text_limit=text_limit,
                list_limit=item_limit,
                dict_limit=dict_limit,
            )
            message[field] = compact_value
            if truncated or value_truncated:
                truncated_fields.add(field)
        elif isinstance(value, dict):
            compact_value, value_truncated = _compact_aux_value(
                value,
                text_limit=text_limit,
                list_limit=item_limit,
                dict_limit=dict_limit,
            )
            message[field] = compact_value
            if value_truncated:
                truncated_fields.add(field)

    if truncated_fields:
        metadata_record = dict(message.get("metadata")) if isinstance(message.get("metadata"), dict) else {}
        public_response = dict(metadata_record.get("public_response")) if isinstance(metadata_record.get("public_response"), dict) else {}
        public_response["truncated"] = True
        public_response["fields"] = sorted(truncated_fields)
        metadata_record["public_response"] = public_response
        message["metadata"] = metadata_record
    return message


def compact_conversation_for_response(
    conversation: dict[str, Any],
    *,
    messages_window: dict[str, Any] | None = None,
    message_text_limit: int = DEFAULT_MESSAGE_TEXT_LIMIT,
) -> dict[str, Any]:
    compact_conversation = dict(conversation)
    messages = compact_conversation.get("messages")
    if not isinstance(messages, list):
        return compact_conversation
    compact_messages: list[dict[str, Any]] = []
    for message_value in messages:
        compact_messages.append(
            compact_message_for_response(
                message_value,
                text_limit=message_text_limit,
            )
        )
    compact_conversation["messages"] = compact_messages
    if messages_window is not None:
        window = dict(messages_window)
        total = int(window.get("total") or 0)
        window["returned"] = len(compact_messages)
        window["truncated"] = bool(window.get("has_more_before") or window.get("has_more_after"))
        compact_conversation["message_count"] = total
        compact_conversation["messages_window"] = window
        compact_conversation["messages_truncated"] = bool(window["truncated"])
    elif "message_count" not in compact_conversation:
        compact_conversation["message_count"] = len(compact_messages)
    return compact_conversation
