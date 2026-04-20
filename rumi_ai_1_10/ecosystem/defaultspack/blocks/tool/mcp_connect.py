import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from _common import ok, error, gen_id, timestamp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.mcp_client import McpClient
from domain.tool.registry import ToolRegistry


def run(input_data, context):
    """defaults.tool.mcp_connect — MCP サーバーに接続する"""
    server_name = input_data.get("server_name")
    if not server_name:
        return error("server_name is required", "MISSING_PARAM")

    config = input_data.get("config")
    if config is None:
        return error("config is required", "MISSING_PARAM")

    transport = config.get("transport", "stdio")
    if transport not in ("stdio", "sse"):
        return error("config.transport must be 'stdio' or 'sse'", "INVALID_PARAM")
    if transport == "stdio" and not config.get("command"):
        return error("config.command is required for stdio transport", "MISSING_PARAM")
    if transport == "sse" and not config.get("url"):
        return error("config.url is required for sse transport", "MISSING_PARAM")

    mcp_client = McpClient()
    try:
        tools_added = mcp_client.connect(server_name, config)
    except Exception as exc:
        return error("MCP connect failed: {}".format(exc), "MCP_CONNECT_ERROR")

    registry = ToolRegistry()
    registry.register_mcp_server(server_name, config)

    server_tools = mcp_client.get_server_tools(server_name)
    for tool in server_tools:
        if not isinstance(tool, dict):
            continue
        tool_name = tool.get("name", "")
        if not tool_name:
            continue
        tool_id = "mcp__{}__{}".format(server_name, tool_name)
        registry.register({
            "tool_id": tool_id,
            "name": tool_name,
            "summary": tool.get("description", ""),
            "tags": ["mcp", server_name],
            "schema": {
                "parameters": tool.get("inputSchema", {})
            },
            "execution": {
                "type": "mcp",
                "server_name": server_name,
                "mcp_tool_name": tool_name,
            },
        })

    return ok({
        "status": "connected",
        "tools_added": tools_added,
    })
