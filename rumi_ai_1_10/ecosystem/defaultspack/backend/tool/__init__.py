"""
tool module - Tool management, invocation, consent, MCP.

Each tool has: UUID, icon, metadata, on/off toggle, consent requirements.
Supports MCP connections, runtime tool creation, and plugin bundles.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolEntry:
    tool_id: str
    uuid: str = field(default_factory=lambda: str(_uuid.uuid4()))
    display_name: str = ""
    description: str = ""
    icon: str = ""
    enabled: bool = True
    requires_consent: bool = False
    consent_message: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    handler: Optional[Callable] = field(default=None, repr=False)
    source: str = "builtin"  # builtin | plugin | mcp | runtime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "uuid": self.uuid,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "enabled": self.enabled,
            "requires_consent": self.requires_consent,
            "input_schema": self.input_schema,
            "tags": self.tags,
            "source": self.source,
        }


class ToolManager:
    """Central tool registry, invocation, and MCP manager."""

    def __init__(self):
        self._lock = threading.RLock()
        self._tools: Dict[str, ToolEntry] = {}
        self._uuid_index: Dict[str, str] = {}
        self._mcp_connections: Dict[str, Any] = {}
        self._consent_log: List[Dict[str, Any]] = []

    def register(self, entry: ToolEntry) -> None:
        with self._lock:
            self._tools[entry.tool_id] = entry
            self._uuid_index[entry.uuid] = entry.tool_id

    def get(self, tool_id: str) -> Optional[ToolEntry]:
        with self._lock:
            return self._tools.get(tool_id)

    def list_all(self) -> List[ToolEntry]:
        with self._lock:
            return list(self._tools.values())

    def list_enabled(self) -> List[ToolEntry]:
        with self._lock:
            return [t for t in self._tools.values() if t.enabled]

    def enable(self, tool_id: str) -> bool:
        with self._lock:
            t = self._tools.get(tool_id)
            if t:
                t.enabled = True
                return True
            return False

    def disable(self, tool_id: str) -> bool:
        with self._lock:
            t = self._tools.get(tool_id)
            if t:
                t.enabled = False
                return True
            return False

    def invoke(self, tool_id: str, input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        tool = self.get(tool_id)
        if tool is None:
            return {"error": f"Tool '{tool_id}' not found"}
        if not tool.enabled:
            return {"error": f"Tool '{tool_id}' is disabled"}
        if tool.handler is None:
            return {"error": f"Tool '{tool_id}' has no handler"}
        try:
            result = tool.handler(input_data or {})
            return {"result": result}
        except Exception as exc:
            return {"error": str(exc)}

    def check_consent(self, tool_id: str) -> Dict[str, Any]:
        tool = self.get(tool_id)
        if tool is None:
            return {"required": False}
        return {
            "required": tool.requires_consent,
            "message": tool.consent_message,
            "tool_id": tool_id,
        }

    def grant_consent(self, tool_id: str, user: str = "system") -> None:
        import time
        self._consent_log.append({
            "tool_id": tool_id,
            "user": user,
            "action": "granted",
            "timestamp": time.time(),
        })

    def connect_mcp(self, server_url: str, name: str = "") -> Dict[str, Any]:
        conn_id = name or server_url
        self._mcp_connections[conn_id] = {
            "url": server_url,
            "name": name,
            "status": "connected",
        }
        return {"connection_id": conn_id, "status": "connected"}

    def disconnect_mcp(self, conn_id: str) -> bool:
        return self._mcp_connections.pop(conn_id, None) is not None

    def list_mcp(self) -> List[Dict[str, Any]]:
        return list(self._mcp_connections.values())

    def get_metadata_index(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [t.to_dict() for t in self._tools.values()]

    def delete(self, tool_id: str) -> bool:
        with self._lock:
            entry = self._tools.pop(tool_id, None)
            if entry:
                self._uuid_index.pop(entry.uuid, None)
                return True
            return False
