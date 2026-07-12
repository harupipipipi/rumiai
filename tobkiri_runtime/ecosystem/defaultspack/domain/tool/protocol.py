from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RumiToolDefinition:
    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderToolDefinition:
    name: str
    provider_alias: str
    provider_payload: dict[str, Any]
    original: RumiToolDefinition
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RumiToolCall:
    id: str
    name: str
    arguments: Any = field(default_factory=dict)
    provider_alias: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RumiToolResult:
    tool_call_id: str
    name: str
    content: Any = ""
    is_error: bool = False
    approval_required: bool = False
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
