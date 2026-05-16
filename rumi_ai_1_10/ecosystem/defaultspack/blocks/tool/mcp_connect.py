import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import error, ok  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.mcp_client import McpClient  # noqa: E402
from domain.tool.mcp_registry import McpRegistry  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402
from blocks.tool._safety import (  # noqa: E402
    approved_or_request,
    record_tool_attempt,
    record_tool_execution,
    record_tool_failure,
)


OPERATION = "tool.mcp_connect"
RISK = "high"


def _mcp_config_path():
    return (
        Path(__file__).resolve().parents[2]
        / "user_data"
        / "shared"
        / "tools"
        / "mcp.json"
    )


def _load_saved_mcp_config(server_identifier):
    registry_server = McpRegistry().get_server(server_identifier)
    if registry_server:
        return dict(registry_server.get("config") or {})
    config_path = _mcp_config_path()
    if not config_path.is_file():
        return None
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if isinstance(raw, dict):
        servers = raw.get("servers", [])
    elif isinstance(raw, list):
        servers = raw
    else:
        return None

    if isinstance(servers, dict):
        servers = list(servers.values())
    if not isinstance(servers, list):
        return None

    for server in servers:
        if not isinstance(server, dict):
            continue
        candidates = {
            str(server.get("server_id", "") or "").strip(),
            str(server.get("name", "") or "").strip(),
        }
        if server_identifier in candidates:
            return dict(server)
    return None


def _resolve_server_name(input_data, config):
    for candidate in (
        input_data.get("server_id"),
        config.get("server_id") if isinstance(config, dict) else None,
        input_data.get("server_name"),
        config.get("name") if isinstance(config, dict) else None,
    ):
        server_name = str(candidate or "").strip()
        if server_name:
            return server_name
    return ""


def _public_tool_name(tool_name, config):
    prefix = ""
    if isinstance(config, dict):
        prefix = str(config.get("tool_prefix", "") or "").strip()
    if prefix:
        return "{}_{}".format(prefix, tool_name)
    return tool_name


def _tool_registry_id(server_name, tool_name, config):
    public_name = _public_tool_name(tool_name, config)
    if public_name != tool_name:
        return public_name
    return "mcp__{}__{}".format(server_name, tool_name)


def run(input_data, context):
    """defaults.tool.mcp_connect - connect to an MCP server."""
    requested_server = str(
        input_data.get("server_id")
        or input_data.get("server_name")
        or ""
    ).strip()
    config = input_data.get("config")
    if config is None and requested_server:
        config = _load_saved_mcp_config(requested_server)

    server_name = _resolve_server_name(input_data, config)
    if not server_name:
        return error("server_name or server_id is required", "MISSING_PARAM")
    if config is None:
        return error(
            "config is required, or provide a server_id present in mcp.json",
            "MISSING_PARAM",
        )

    transport = config.get("transport", "stdio")
    if transport not in ("stdio", "sse"):
        return error("config.transport must be 'stdio' or 'sse'", "INVALID_PARAM")
    if transport == "stdio" and not config.get("command"):
        return error("config.command is required for stdio transport", "MISSING_PARAM")
    if transport == "sse" and not config.get("url"):
        return error("config.url is required for sse transport", "MISSING_PARAM")

    record_tool_attempt(OPERATION, RISK, input_data)
    approval = approved_or_request(input_data, context, OPERATION, RISK)
    if approval is not None:
        return approval

    mcp_registry = McpRegistry()
    mcp_registry.add_server({"server_id": server_name, "name": server_name, "config": config})

    mcp_client = McpClient()
    try:
        tools_added = mcp_client.connect(server_name, config)
    except Exception as exc:
        record_tool_failure(OPERATION, RISK, input_data, str(exc), server_name=server_name)
        return error("MCP connect failed: {}".format(exc), "MCP_CONNECT_ERROR")

    registry = ToolRegistry()
    registry.register_mcp_server(server_name, config)

    server_tools = mcp_client.get_server_tools(server_name)
    registered_tools = []
    for tool in server_tools:
        if not isinstance(tool, dict):
            continue
        tool_name = tool.get("name", "")
        if not tool_name:
            continue
        public_name = _public_tool_name(tool_name, config)
        tool_id = _tool_registry_id(server_name, tool_name, config)
        server_id = str(config.get("server_id", "") or server_name)
        description = str(tool.get("description", "") or "")
        registered_tools.append(tool_id)
        registry.register(
            {
                "tool_id": tool_id,
                "name": public_name,
                "summary": description,
                "tags": ["mcp", server_name],
                "schema": {"parameters": tool.get("inputSchema", {})},
                "execution": {
                    "type": "mcp",
                    "server_name": server_name,
                    "mcp_tool_name": tool_name,
                },
                "category": "tool",
                "ui": {
                    "group_id": "mcp",
                    "group_label": "MCP",
                    "group_icon": "terminal",
                    "label": public_name,
                    "description": description,
                    "keywords": " ".join(["mcp", server_name, server_id, tool_name, public_name]),
                },
                "metadata": {
                    "source": "mcp",
                    "server_id": server_id,
                    "server_name": server_name,
                    "mcp_tool_name": tool_name,
                    "transport": transport,
                    "description": description,
                },
            }
        )

    record_tool_execution(OPERATION, RISK, input_data, server_name=server_name, tools_added=tools_added)
    mcp_registry.mark_connected(server_name, tools=registered_tools, approved=True)
    return ok(
        {
            "server_id": str(config.get("server_id", "") or server_name),
            "server_name": server_name,
            "status": "connected",
            "tools_added": tools_added,
            "tools": registered_tools,
            "permission": {"approved": True, "source": "approval"},
            "server": {
                "name": server_name,
                "transport": transport,
                "config": registry.list_mcp_servers().get(server_name, {}),
            },
        }
    )
