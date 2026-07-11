from __future__ import annotations

from blocks._common import error, ok
from domain.tool.mcp_approval import obsolete_mcp_approvals
from domain.tool.mcp_registry import McpRegistry


def run(input_data, context=None):
    del context
    registry = McpRegistry()
    method = str(input_data.get("_method") or input_data.get("method") or "GET").upper()
    action = str(input_data.get("action") or "").strip().lower()
    try:
        if method == "GET" or action == "list":
            servers = registry.list_servers()
            return ok({"servers": servers, "count": len(servers)})
        if method == "POST" or action in {"add", "create", "upsert"}:
            payload = (
                input_data.get("server")
                if isinstance(input_data.get("server"), dict)
                else input_data
            )
            server = registry.add_server(payload)
            obsolete_mcp_approvals(
                str(server.get("server_id") or ""),
                reason="MCP server configuration was updated",
            )
            return ok({"server": server})
        if method == "DELETE" or action in {"delete", "remove"}:
            server_id = str(
                input_data.get("server_id")
                or input_data.get("server_name")
                or input_data.get("name")
                or ""
            ).strip()
            if not server_id:
                return error("'server_id' is required", code="INVALID_INPUT")
            deleted = registry.delete_server(server_id)
            if deleted:
                obsolete_mcp_approvals(
                    server_id,
                    reason="MCP server configuration was deleted",
                )
            return ok({"server_id": server_id, "deleted": deleted})
        return error("unsupported method: " + method, code="INVALID_INPUT")
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="MCP_REGISTRY_ERROR")
