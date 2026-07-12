from __future__ import annotations

import json
from typing import Any

from blocks._common import gen_id
from domain.chat.ir import RumiChatIR, RumiIRMessage
from domain.chat.ir_blocks import IR_SCHEMA_VERSION, RumiIRBlock, RumiToolCallIR, RumiToolResultIR
from domain.chat.ir_validation import normalize_ir


def stored_messages_to_ir(conversation_id: str, messages: list[dict[str, Any]]) -> RumiChatIR:
    ir_messages: list[RumiIRMessage] = []
    for message in list(messages or []):
        if not isinstance(message, dict):
            continue
        content = message.get("content", [])
        extra: dict[str, Any] = {}
        if isinstance(content, str):
            extra["source_content_kind"] = "string"
            blocks = [RumiIRBlock(type="text", text=content)]
        elif isinstance(content, list):
            blocks = [_stored_block_to_ir(block) for block in content]
        else:
            extra["source_content_kind"] = type(content).__name__
            blocks = [RumiIRBlock(type="text", text=str(content or ""))]
        ir_messages.append(
            RumiIRMessage(
                id=str(message.get("id") or ""),
                conversation_id=str(message.get("conversation_id") or conversation_id or ""),
                parent_id=message.get("parent_id"),
                children_ids=list(message.get("children_ids") or []),
                sequence_number=message.get("sequence_number"),
                created_at=message.get("created_at"),
                role=str(message.get("role") or "user"),
                content=blocks,
                metadata=dict(message.get("metadata") or {}),
                usage=dict(message.get("usage") or {}),
                events=list(message.get("events") or []),
                tool_logs=list(message.get("tool_logs") or []),
                model=str(message.get("model") or ""),
                extra=extra,
            )
        )
    return normalize_ir(RumiChatIR(conversation_id=str(conversation_id or ""), messages=ir_messages))


def ir_to_stored_messages(ir: RumiChatIR) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for message in normalize_ir(ir).messages:
        content: Any
        if message.extra.get("source_content_kind") == "string" and len(message.content) == 1:
            content = message.content[0].text
        else:
            content = [_ir_block_to_stored_block(block) for block in message.content]
        payload: dict[str, Any] = {
            "role": message.role,
            "content": content,
        }
        for key, value in {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "parent_id": message.parent_id,
            "children_ids": message.children_ids,
            "sequence_number": message.sequence_number,
            "created_at": message.created_at,
            "metadata": message.metadata,
            "usage": message.usage,
            "events": message.events,
            "tool_logs": message.tool_logs,
            "model": message.model,
        }.items():
            if value not in (None, "", [], {}):
                payload[key] = value
        messages.append(payload)
    return messages


def _legacy_metadata(message: RumiIRMessage, include_metadata: bool) -> dict[str, Any]:
    if not include_metadata or not isinstance(message.metadata, dict) or not message.metadata:
        return {}
    return {"metadata": dict(message.metadata)}


def ir_to_legacy_standard_messages(ir: RumiChatIR, *, include_metadata: bool = False) -> list[dict[str, Any]]:
    standard: list[dict[str, Any]] = []
    for message in normalize_ir(ir).messages:
        role = message.role or "user"
        if message.extra.get("source_content_kind") == "string" and len(message.content) == 1:
            standard.append({"role": role, "content": message.content[0].text, **_legacy_metadata(message, include_metadata)})
            continue
        text_parts: list[Any] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        for block in message.content:
            if block.type == "reasoning" and not block.model_visible:
                continue
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "image_url":
                text_parts.append(_ir_block_to_stored_block(block))
            elif block.type == "image" and block.data.get("source"):
                text_parts.append(_ir_block_to_stored_block(block))
            elif block.type in {"audio", "input_audio"}:
                text_parts.append(_ir_block_to_stored_block(block))
            elif block.type == "tool_call" and block.tool_call is not None:
                tool_calls.append(
                    {
                        "id": block.tool_call.id,
                        "type": "function",
                        "function": {
                            "name": block.tool_call.provider_alias or block.tool_call.name,
                            "arguments": block.tool_call.arguments,
                        },
                    }
                )
            elif block.type == "tool_result" and block.tool_result is not None:
                tool_results.append(
                    {
                        "tool_call_id": block.tool_result.tool_call_id,
                        "content": block.tool_result.content,
                        **({"name": block.tool_result.name} if block.tool_result.name else {}),
                    }
                )
            else:
                stored = _ir_block_to_stored_block(block)
                text_parts.append(stored.get("text", str(stored)) if isinstance(stored, dict) else str(stored))
        if role == "tool" or (not text_parts and not tool_calls and tool_results):
            for tool_result in tool_results:
                standard.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_result.get("tool_call_id", ""),
                        **({"name": tool_result.get("name", "")} if tool_result.get("name") else {}),
                        "content": tool_result.get("content", ""),
                        **_legacy_metadata(message, include_metadata),
                    }
                )
            continue
        entry: dict[str, Any] = {"role": role, **_legacy_metadata(message, include_metadata)}
        if tool_calls:
            string_parts = [part for part in text_parts if isinstance(part, str) and part]
            entry["content"] = "\n".join(string_parts) if string_parts else None
            entry["tool_calls"] = tool_calls
        elif any(isinstance(part, dict) for part in text_parts):
            content = []
            for part in text_parts:
                if isinstance(part, dict):
                    content.append(part)
                elif part:
                    content.append({"type": "text", "text": part})
            entry["content"] = content
        else:
            entry["content"] = "\n".join(str(part) for part in text_parts if part) or ""
        if tool_results:
            for tool_result in tool_results:
                standard.append(entry)
                standard.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_result.get("tool_call_id", ""),
                        **({"name": tool_result.get("name", "")} if tool_result.get("name") else {}),
                        "content": tool_result.get("content", ""),
                        **_legacy_metadata(message, include_metadata),
                    }
                )
            continue
        standard.append(entry)
    return standard


def legacy_standard_messages_to_ir(messages: list[dict[str, Any]], conversation_id: str = "") -> RumiChatIR:
    stored: list[dict[str, Any]] = []
    for index, message in enumerate(list(messages or [])):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        content = message.get("content", "")
        blocks: list[Any] = []
        if isinstance(content, list):
            blocks.extend(content)
        elif content not in (None, ""):
            blocks.append({"type": "text", "text": str(content)})
        if message.get("tool_calls"):
            for tool_call in message.get("tool_calls") or []:
                function_def = tool_call.get("function") if isinstance(tool_call, dict) else {}
                blocks.append(
                    {
                        "type": "tool_call",
                        "id": str(tool_call.get("id") or "") if isinstance(tool_call, dict) else "",
                        "name": str(function_def.get("name") or ""),
                        "arguments": function_def.get("arguments", ""),
                    }
                )
        if role == "tool":
            blocks = [
                {
                    "type": "tool_result",
                    "tool_call_id": str(message.get("tool_call_id") or ""),
                    "name": str(message.get("name") or ""),
                    "content": message.get("content", ""),
                }
            ]
        metadata = dict(message.get("metadata") or {}) if isinstance(message.get("metadata"), dict) else {}
        for fallback_key in ("raw_text", "text", "prompt", "message"):
            fallback_value = message.get(fallback_key)
            if isinstance(fallback_value, str) and fallback_value.strip():
                metadata.setdefault(fallback_key, fallback_value)
        stored_message = {
            "id": str(message.get("id") or f"provider-message-{index + 1}"),
            "conversation_id": conversation_id,
            "role": role,
            "content": blocks,
        }
        if metadata:
            stored_message["metadata"] = metadata
        stored.append(stored_message)
    return stored_messages_to_ir(conversation_id, stored)


def append_assistant_tool_use_to_ir(
    ir: RumiChatIR,
    tool_uses: list[dict[str, Any]],
    *,
    reasoning_content: str = "",
) -> RumiChatIR:
    blocks: list[RumiIRBlock] = []
    if reasoning_content:
        blocks.append(RumiIRBlock(type="reasoning", text=reasoning_content, model_visible=False))
    for block in tool_uses or []:
        if not isinstance(block, dict):
            continue
        blocks.append(
            RumiIRBlock(
                type="tool_call",
                tool_call=RumiToolCallIR(
                    id=str(block.get("id") or block.get("tool_call_id") or gen_id()),
                    name=str(block.get("name") or block.get("tool_name") or ""),
                    arguments=block.get("input", block.get("arguments", "{}")),
                ),
            )
        )
    ir.messages.append(
        RumiIRMessage(
            id=gen_id(),
            conversation_id=ir.conversation_id,
            role="assistant",
            content=blocks,
            extra={"ephemeral_provider_turn": True},
        )
    )
    return ir


def append_tool_result_to_ir(
    ir: RumiChatIR,
    tool_name: str,
    result: Any,
    tool_call_id: str,
    *,
    model: str = "",
) -> RumiChatIR:
    content = _tool_result_content(result)
    ir.messages.append(
        RumiIRMessage(
            id=gen_id(),
            conversation_id=ir.conversation_id,
            role="tool",
            content=[
                RumiIRBlock(
                    type="tool_result",
                    tool_result=RumiToolResultIR(
                        tool_call_id=tool_call_id,
                        name=tool_name,
                        content=content,
                        is_error=_result_is_error(result),
                    ),
                )
            ],
            model=model,
            extra={"ephemeral_provider_turn": True},
        )
    )
    return ir


def _stored_block_to_ir(block: Any) -> RumiIRBlock:
    if not isinstance(block, dict):
        return RumiIRBlock(type="text", text=str(block))
    block_type = str(block.get("type") or "text")
    if block_type == "tool_call":
        return RumiIRBlock(
            type="tool_call",
            tool_call=RumiToolCallIR(
                id=str(block.get("id") or ""),
                name=str(block.get("name") or ""),
                arguments=block.get("arguments", ""),
                provider_alias=str(block.get("provider_alias") or ""),
            ),
            original=dict(block),
        )
    if block_type == "tool_result":
        return RumiIRBlock(
            type="tool_result",
            tool_result=RumiToolResultIR(
                tool_call_id=str(block.get("tool_call_id") or ""),
                name=str(block.get("name") or ""),
                content=block.get("content", ""),
                is_error=bool(block.get("is_error", False)),
                approval_required=bool(block.get("approval_required", False)),
                artifacts=list(block.get("artifacts") or []),
            ),
            original=dict(block),
        )
    data = {key: value for key, value in block.items() if key not in {"type", "text"}}
    return RumiIRBlock(
        type=block_type if block_type else "unknown",
        text=str(block.get("text") or ""),
        data=data,
        model_visible=bool(block.get("model_visible", True)),
        original=dict(block),
    )


def _ir_block_to_stored_block(block: RumiIRBlock) -> dict[str, Any]:
    if block.original is not None and block.type not in {"tool_call", "tool_result"}:
        return dict(block.original)
    if block.type == "tool_call" and block.tool_call is not None:
        return {
            "type": "tool_call",
            "id": block.tool_call.id,
            "name": block.tool_call.name,
            "arguments": block.tool_call.arguments,
        }
    if block.type == "tool_result" and block.tool_result is not None:
        return {
            "type": "tool_result",
            "tool_call_id": block.tool_result.tool_call_id,
            **({"name": block.tool_result.name} if block.tool_result.name else {}),
            "content": block.tool_result.content,
        }
    payload = {"type": block.type}
    if block.text:
        payload["text"] = block.text
    payload.update(block.data)
    return payload


def _tool_result_content(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return str(result)


def _result_is_error(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("status") == "error" or result.get("is_error") is True:
        return True
    data = result.get("data")
    return isinstance(data, dict) and data.get("is_error") is True
