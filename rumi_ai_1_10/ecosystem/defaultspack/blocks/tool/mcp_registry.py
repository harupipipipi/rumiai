from __future__ import annotations

from typing import Any

from blocks._common import error, ok
from domain.tool.mcp_approval import obsolete_mcp_approvals
from domain.tool.mcp_client import McpClient
from domain.tool.mcp_registry import McpRegistry
from domain.tool.registry import ToolRegistry


def _server_identifier(input_data: dict[str, Any]) -> str:
    return str(
        input_data.get("server_id")
        or input_data.get("server_name")
        or input_data.get("name")
        or ""
    ).strip()


def _canonical_server(registry: McpRegistry, requested: str) -> tuple[str, str] | None:
    server = registry.get_server(requested)
    if not isinstance(server, dict):
        return None
    server_id = str(server.get("server_id") or requested).strip()
    server_name = str(server.get("name") or server_id).strip()
    return server_id, server_name


def _matches_mcp_server(tool: dict[str, Any], identifiers: set[str]) -> bool:
    execution = tool.get("execution") if isinstance(tool.get("execution"), dict) else {}
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    if str(execution.get("type") or "").strip() != "mcp":
        return False
    candidates = {
        str(execution.get("server_id") or "").strip(),
        str(execution.get("server_name") or "").strip(),
        str(metadata.get("server_id") or "").strip(),
        str(metadata.get("server_name") or "").strip(),
    }
    candidates.discard("")
    return bool(candidates & identifiers)


def _remove_projected_tools(server_id: str, server_name: str) -> list[str]:
    registry = ToolRegistry()
    identifiers = {value for value in (server_id, server_name) if value}
    removed: list[str] = []
    for tool in registry.list_tools():
        if not isinstance(tool, dict) or not _matches_mcp_server(tool, identifiers):
            continue
        tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip()
        if not tool_id:
            continue
        registry.unregister(tool_id)
        removed.append(tool_id)
    return removed


def _disconnect_runtime(server_id: str, server_name: str) -> list[str]:
    # Disconnect is intentionally idempotent. A registration can survive an app
    # restart even when its process is no longer present in this McpClient.
    client = McpClient()
    client.disconnect(server_name)
    if server_name != server_id:
        client.disconnect(server_id)
    return _remove_projected_tools(server_id, server_name)


def run_disconnect(input_data, context=None):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    requested = _server_identifier(data)
    if not requested:
        return error("'server_id' is required", code="INVALID_INPUT")

    registry = McpRegistry()
    canonical = _canonical_server(registry, requested)
    if canonical is None:
        return error("MCP server is not registered", code="MCP_SERVER_NOT_FOUND")
    server_id, server_name = canonical

    removed_tools = _disconnect_runtime(server_id, server_name)
    registry.mark_connected(
        server_id,
        status="disconnected",
        tools=[],
        approved=registry.is_approved(server_id),
    )
    obsolete_mcp_approvals(server_id, reason="MCP server was disconnected")
    return ok(
        {
            "server_id": server_id,
            "server_name": server_name,
            "status": "disconnected",
            "connected": False,
            "removed_tools": removed_tools,
        }
    )


def run_remove(input_data, context=None):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    requested = _server_identifier(data)
    if not requested:
        return error("'server_id' is required", code="INVALID_INPUT")

    registry = McpRegistry()
    canonical = _canonical_server(registry, requested)
    if canonical is None:
        return error("MCP server is not registered", code="MCP_SERVER_NOT_FOUND")
    server_id, server_name = canonical

    removed_tools = _disconnect_runtime(server_id, server_name)
    deleted = registry.delete_server(server_id)
    if not deleted:
        return error(
            "MCP server registration could not be removed",
            code="MCP_REMOVE_FAILED",
        )
    obsolete_mcp_approvals(
        server_id,
        reason="MCP server configuration was deleted",
    )
    return ok(
        {
            "server_id": server_id,
            "server_name": server_name,
            "status": "removed",
            "connected": False,
            "deleted": True,
            "removed_tools": removed_tools,
        }
    )


def run(input_data, context=None):
    data = input_data if isinstance(input_data, dict) else {}
    registry = McpRegistry()
    method = str(data.get("_method") or data.get("method") or "GET").upper()
    action = str(data.get("action") or "").strip().lower()
    try:
        if method == "GET" or action == "list":
            servers = registry.list_servers()
            return ok({"servers": servers, "count": len(servers)})
        if method == "POST" or action in {"add", "create", "upsert"}:
            payload = data.get("server") if isinstance(data.get("server"), dict) else data
            server = registry.add_server(payload)
            obsolete_mcp_approvals(
                str(server.get("server_id") or ""),
                reason="MCP server configuration was updated",
            )
            return ok({"server": server})
        if method == "DELETE" or action in {"delete", "remove"}:
            return run_remove(data, context)
        return error("unsupported method: " + method, code="INVALID_INPUT")
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="MCP_REGISTRY_ERROR")
