from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MCPTransport = Literal["stdio", "http", "sse"]
ToolRiskLevel = Literal["read", "write", "dangerous"]
ApprovalMode = Literal["always", "once_per_session", "never_for_read", "profile_policy"]


@dataclass(frozen=True)
class MCPServerDefinition:
    server_id: str
    display_name: str
    transport: MCPTransport
    endpoint: str | None = None
    command: list[str] | None = None
    required_connection_id: str | None = None
    required_provider_id: str | None = None
    enabled: bool = True
    profile_bindings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MCPToolDefinition:
    tool_id: str
    server_id: str
    display_name: str
    description: str
    risk_level: ToolRiskLevel
    required_capabilities: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass(frozen=True)
class ToolPermissionPolicy:
    tool_id: str
    approval_mode: ApprovalMode
    allowed_profiles: list[str] = field(default_factory=list)
    audit: bool = True
