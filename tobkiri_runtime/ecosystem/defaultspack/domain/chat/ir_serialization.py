from __future__ import annotations

from typing import Any

from domain.chat.ir import RumiChatIR, RumiIRMessage
from domain.chat.ir_blocks import (
    IR_SCHEMA_VERSION,
    BridgeAction,
    DroppedFeature,
    ProviderWarning,
    RumiIRBlock,
    RumiToolCallIR,
    RumiToolResultIR,
)


def block_from_dict(raw: Any) -> RumiIRBlock:
    if not isinstance(raw, dict):
        return RumiIRBlock(type="text", text=str(raw))
    block_type = str(raw.get("type") or "text")
    tool_call = None
    if block_type == "tool_call":
        tool_raw = raw.get("tool_call") if isinstance(raw.get("tool_call"), dict) else raw
        tool_call = RumiToolCallIR(
            id=str(tool_raw.get("id") or ""),
            name=str(tool_raw.get("name") or ""),
            arguments=tool_raw.get("arguments", ""),
            provider_alias=str(tool_raw.get("provider_alias") or ""),
            metadata=dict(tool_raw.get("metadata") or {}),
        )
    tool_result = None
    if block_type == "tool_result":
        result_raw = raw.get("tool_result") if isinstance(raw.get("tool_result"), dict) else raw
        tool_result = RumiToolResultIR(
            tool_call_id=str(result_raw.get("tool_call_id") or ""),
            name=str(result_raw.get("name") or ""),
            content=result_raw.get("content", ""),
            is_error=bool(result_raw.get("is_error", False)),
            approval_required=bool(result_raw.get("approval_required", False)),
            artifacts=list(result_raw.get("artifacts") or []),
            metadata=dict(result_raw.get("metadata") or {}),
        )
    data = {
        key: value
        for key, value in raw.items()
        if key
        not in {
            "schema_version",
            "type",
            "text",
            "tool_call",
            "tool_result",
            "model_visible",
            "original",
        }
    }
    return RumiIRBlock(
        schema_version=str(raw.get("schema_version") or IR_SCHEMA_VERSION),
        type=block_type,
        text=str(raw.get("text") or ""),
        data=data,
        tool_call=tool_call,
        tool_result=tool_result,
        model_visible=bool(raw.get("model_visible", True)),
        original=raw.get("original") if isinstance(raw.get("original"), dict) else None,
    )


def message_from_dict(raw: dict[str, Any]) -> RumiIRMessage:
    return RumiIRMessage(
        schema_version=str(raw.get("schema_version") or IR_SCHEMA_VERSION),
        id=str(raw.get("id") or ""),
        conversation_id=str(raw.get("conversation_id") or ""),
        parent_id=raw.get("parent_id"),
        children_ids=list(raw.get("children_ids") or []),
        sequence_number=raw.get("sequence_number"),
        created_at=raw.get("created_at"),
        role=str(raw.get("role") or "user"),
        content=[block_from_dict(block) for block in raw.get("content", []) if block is not None],
        metadata=dict(raw.get("metadata") or {}),
        usage=dict(raw.get("usage") or {}),
        events=list(raw.get("events") or []),
        tool_logs=list(raw.get("tool_logs") or []),
        model=str(raw.get("model") or ""),
        extra=dict(raw.get("extra") or {}),
    )


def ir_from_dict(raw: dict[str, Any]) -> RumiChatIR:
    warnings = [
        ProviderWarning(
            code=str(item.get("code") or ""),
            message=str(item.get("message") or ""),
            severity=str(item.get("severity") or "warning"),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in raw.get("warnings", [])
        if isinstance(item, dict)
    ]
    dropped = [
        DroppedFeature(
            feature=str(item.get("feature") or ""),
            reason=str(item.get("reason") or ""),
            source=str(item.get("source") or ""),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in raw.get("dropped_features", [])
        if isinstance(item, dict)
    ]
    bridges = [
        BridgeAction(
            action=str(item.get("action") or ""),
            reason=str(item.get("reason") or ""),
            status=str(item.get("status") or "planned"),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in raw.get("bridge_actions", [])
        if isinstance(item, dict)
    ]
    return RumiChatIR(
        schema_version=str(raw.get("schema_version") or IR_SCHEMA_VERSION),
        conversation_id=str(raw.get("conversation_id") or ""),
        messages=[message_from_dict(message) for message in raw.get("messages", []) if isinstance(message, dict)],
        metadata=dict(raw.get("metadata") or {}),
        warnings=warnings,
        dropped_features=dropped,
        bridge_actions=bridges,
    )


def ir_to_dict(ir: RumiChatIR) -> dict[str, Any]:
    return ir.to_dict()
