from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.chat.ir_blocks import (
    IR_SCHEMA_VERSION,
    BridgeAction,
    DroppedFeature,
    ProviderWarning,
    RumiIRBlock,
)


@dataclass
class RumiUsageIR:
    schema_version: str = IR_SCHEMA_VERSION
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            **({"metadata": self.metadata} if self.metadata else {}),
        }


@dataclass
class RumiIRMessage:
    schema_version: str = IR_SCHEMA_VERSION
    id: str = ""
    conversation_id: str = ""
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    sequence_number: int | None = None
    created_at: Any = None
    role: str = "user"
    content: list[RumiIRBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_logs: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": [block.to_dict() for block in self.content],
        }
        optional = {
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "sequence_number": self.sequence_number,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "usage": self.usage,
            "events": self.events,
            "tool_logs": self.tool_logs,
            "model": self.model,
            "extra": self.extra,
        }
        for key, value in optional.items():
            if value not in (None, "", [], {}):
                payload[key] = value
        return payload


@dataclass
class RumiChatIR:
    schema_version: str = IR_SCHEMA_VERSION
    conversation_id: str = ""
    messages: list[RumiIRMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[ProviderWarning] = field(default_factory=list)
    dropped_features: list[DroppedFeature] = field(default_factory=list)
    bridge_actions: list[BridgeAction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "conversation_id": self.conversation_id,
            "messages": [message.to_dict() for message in self.messages],
            **({"metadata": self.metadata} if self.metadata else {}),
            **({"warnings": [warning.to_dict() for warning in self.warnings]} if self.warnings else {}),
            **(
                {"dropped_features": [feature.to_dict() for feature in self.dropped_features]}
                if self.dropped_features
                else {}
            ),
            **(
                {"bridge_actions": [action.to_dict() for action in self.bridge_actions]}
                if self.bridge_actions
                else {}
            ),
        }


@dataclass
class RumiResponseIR:
    schema_version: str = IR_SCHEMA_VERSION
    content: list[RumiIRBlock] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: RumiUsageIR = field(default_factory=RumiUsageIR)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_extra: dict[str, Any] = field(default_factory=dict)

    def to_standard_response(self) -> dict[str, Any]:
        return {
            "content": [_block_to_standard_content(block) for block in self.content],
            "finish_reason": self.finish_reason,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "metadata": dict(self.metadata),
            **({"raw_extra": self.raw_extra} if self.raw_extra else {}),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "content": [block.to_dict() for block in self.content],
            "finish_reason": self.finish_reason,
            "usage": self.usage.to_dict(),
            **({"metadata": self.metadata} if self.metadata else {}),
            **({"raw_extra": self.raw_extra} if self.raw_extra else {}),
        }


@dataclass
class RumiStreamEventIR:
    schema_version: str = IR_SCHEMA_VERSION
    type: str = ""
    delta: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "type": self.type,
            **({"delta": self.delta} if self.delta else {}),
            **({"finish_reason": self.finish_reason} if self.finish_reason else {}),
            **({"usage": self.usage} if self.usage else {}),
            **({"metadata": self.metadata} if self.metadata else {}),
        }


def _block_to_standard_content(block: RumiIRBlock) -> dict[str, Any]:
    if block.type == "tool_call" and block.tool_call is not None:
        return {
            "type": "tool_use",
            "id": block.tool_call.id,
            "name": block.tool_call.name,
            "input": block.tool_call.arguments,
        }
    if block.type == "tool_result" and block.tool_result is not None:
        return {
            "type": "tool_result",
            "tool_call_id": block.tool_result.tool_call_id,
            "content": block.tool_result.content,
        }
    if block.original is not None and block.type not in {"text", "reasoning"}:
        return dict(block.original)
    payload = {"type": block.type}
    if block.text:
        payload["text"] = block.text
    payload.update(block.data)
    return payload
