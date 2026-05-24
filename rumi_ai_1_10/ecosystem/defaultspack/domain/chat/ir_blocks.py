from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


IR_SCHEMA_VERSION = "rumi.chat.ir.v2"


@dataclass
class RumiToolCallIR:
    schema_version: str = IR_SCHEMA_VERSION
    id: str = ""
    name: str = ""
    arguments: Any = ""
    provider_alias: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            **({"provider_alias": self.provider_alias} if self.provider_alias else {}),
            **({"metadata": self.metadata} if self.metadata else {}),
        }


@dataclass
class RumiToolResultIR:
    schema_version: str = IR_SCHEMA_VERSION
    tool_call_id: str = ""
    name: str = ""
    content: Any = ""
    is_error: bool = False
    approval_required: bool = False
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool_call_id": self.tool_call_id,
            **({"name": self.name} if self.name else {}),
            "content": self.content,
            **({"is_error": self.is_error} if self.is_error else {}),
            **({"approval_required": self.approval_required} if self.approval_required else {}),
            **({"artifacts": self.artifacts} if self.artifacts else {}),
            **({"metadata": self.metadata} if self.metadata else {}),
        }


@dataclass
class RumiIRBlock:
    schema_version: str = IR_SCHEMA_VERSION
    type: str = "text"
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    tool_call: RumiToolCallIR | None = None
    tool_result: RumiToolResultIR | None = None
    model_visible: bool = True
    original: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "type": self.type,
        }
        if self.text:
            payload["text"] = self.text
        if self.data:
            payload.update(self.data)
        if self.tool_call is not None:
            payload["tool_call"] = self.tool_call.to_dict()
        if self.tool_result is not None:
            payload["tool_result"] = self.tool_result.to_dict()
        if self.model_visible is False:
            payload["model_visible"] = False
        if self.original is not None:
            payload["original"] = self.original
        return payload


@dataclass
class ProviderWarning:
    code: str
    message: str
    severity: str = "warning"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            **({"metadata": self.metadata} if self.metadata else {}),
        }


@dataclass
class DroppedFeature:
    feature: str
    reason: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "reason": self.reason,
            **({"source": self.source} if self.source else {}),
            **({"metadata": self.metadata} if self.metadata else {}),
        }


@dataclass
class BridgeAction:
    action: str
    reason: str
    status: str = "planned"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "status": self.status,
            **({"metadata": self.metadata} if self.metadata else {}),
        }
