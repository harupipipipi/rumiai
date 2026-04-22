"""tool module - tool registry, MCP, and consent integration."""

from __future__ import annotations

from importlib import import_module

__all__ = ["MCPConnector", "ToolDefinition", "ToolEntry", "ToolManager"]

_EXPORTS = {
    "MCPConnector": ("mcp_connector", "MCPConnector"),
    "ToolDefinition": ("tool_manager", "ToolDefinition"),
    "ToolEntry": ("tool_manager", "ToolEntry"),
    "ToolManager": ("tool_manager", "ToolManager"),
}

_MODULE_PREFIXES = (
    __name__,
    "ecosystem.defaultspack.backend.tool",
    "rumi_ai_1_10.ecosystem.defaultspack.backend.tool",
)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    last_error = None
    for prefix in _MODULE_PREFIXES:
        try:
            module = import_module(f"{prefix}.{module_name}")
            value = getattr(module, attr_name)
            globals()[name] = value
            return value
        except (ImportError, AttributeError) as exc:
            last_error = exc

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from last_error
