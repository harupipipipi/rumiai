import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import ok  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.mcp_client import McpClient  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402


def run(input_data, context):
    """defaults.tool.mcp_list - return connected MCP servers and tool details."""
    mcp_client = McpClient()
    registry = ToolRegistry()
    registry_servers = registry.list_mcp_servers()
    servers = mcp_client.list_servers()
    requested_server = str(
        input_data.get("server_id")
        or input_data.get("server_name")
        or ""
    ).strip()

    detailed_servers = []
    for srv in servers:
        server_name = srv.get("name", "")
        registered_config = registry_servers.get(server_name, {})
        server_id = str(registered_config.get("server_id", "") or server_name)
        if requested_server and requested_server not in {server_name, server_id}:
            continue

        raw_tools = mcp_client.get_server_tools(server_name)
        tool_details = []
        for tool in raw_tools:
            if isinstance(tool, dict):
                tool_details.append(
                    {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "inputSchema": tool.get("inputSchema", {}),
                    }
                )
            else:
                tool_details.append(
                    {"name": str(tool), "description": "", "inputSchema": {}}
                )
        detailed_servers.append(
            {
                "name": server_name,
                "server_name": server_name,
                "server_id": server_id,
                "status": srv.get("status", "unknown"),
                "tools": srv.get("tools", []),
                "tool_details": tool_details,
                "registered_config": registered_config,
            }
        )

    return ok({"servers": detailed_servers, "count": len(detailed_servers)})
