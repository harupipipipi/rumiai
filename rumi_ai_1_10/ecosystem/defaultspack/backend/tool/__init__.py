"""tool module - tool registry, MCP, and consent integration."""

from .mcp_connector import MCPConnector
from .tool_manager import ToolDefinition, ToolEntry, ToolManager

__all__ = ["MCPConnector", "ToolDefinition", "ToolEntry", "ToolManager"]
