import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from _common import ok, error, gen_id, timestamp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.mcp_client import McpClient


def run(input_data, context):
    """defaults.tool.mcp_list — 接続中 MCP サーバーとツール一覧を返す"""
    mcp_client = McpClient()
    servers = mcp_client.list_servers()

    detailed_servers = []
    for srv in servers:
        server_name = srv.get("name", "")
        raw_tools = mcp_client.get_server_tools(server_name)
        tool_details = []
        for t in raw_tools:
            if isinstance(t, dict):
                tool_details.append({
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "inputSchema": t.get("inputSchema", {}),
                })
            else:
                tool_details.append({"name": str(t), "description": "", "inputSchema": {}})
        detailed_servers.append({
            "name": server_name,
            "status": srv.get("status", "unknown"),
            "tools": srv.get("tools", []),
            "tool_details": tool_details,
        })

    return ok({"servers": detailed_servers})
