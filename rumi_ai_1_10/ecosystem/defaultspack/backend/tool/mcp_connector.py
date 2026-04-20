"""MCP connector compatibility layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MCPServer:
    server_id: str = ""
    url: str = ""
    connected: bool = False
    tools: List[Dict[str, Any]] = field(default_factory=list)


class MCPConnector:
    """Very small in-memory MCP server registry."""

    def __init__(self) -> None:
        self._servers: Dict[str, MCPServer] = {}

    async def connect(self, server_id: str, url: str) -> MCPServer:
        server = MCPServer(server_id=server_id, url=url, connected=True)
        self._servers[server_id] = server
        return server

    async def disconnect(self, server_id: str) -> bool:
        server = self._servers.get(server_id)
        if server is None:
            return False
        server.connected = False
        return True

    def list_servers(self) -> List[MCPServer]:
        return list(self._servers.values())

    def list_tools(self, server_id: str) -> List[Dict[str, Any]]:
        server = self._servers.get(server_id)
        return list(server.tools) if server else []

    def is_connected(self, server_id: str) -> bool:
        server = self._servers.get(server_id)
        return bool(server and server.connected)
