from __future__ import annotations

from typing import Any

from blocks._common import error, ok
from blocks.tool._safety import (
    approved_or_request,
    record_tool_attempt,
    record_tool_execution,
    record_tool_failure,
)
from domain.tool.mcp_client import McpClient
from domain.tool.mcp_registry import McpRegistry
from domain.tool.registry import ToolRegistry


def _server_id(input_data: dict[str, Any]) -> str:
    return str(
        input_data.get("server_id")
        or input_data.get("server_name")
        or input_data.get("name")
        or ""
    ).strip()


def _tool_matches_server(tool: dict[str, Any], server_id: str) -> bool:
    execution = tool.get("execution") if isinstance(tool.get("execution"), dict) else {}
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    return bool(
        execution.get("type") == "mcp"
        and server_id
        in {
            str(execution.get("server_name") or "").strip(),
            str(metadata.get("server_id") or "").strip(),
            str(metadata.get("server_name") or "").strip(),
        }
    )


def _disconnect_runtime(server_id: str) -> list[str]:
    McpClient().disconnect(server_id)
    registry = ToolRegistry()
    removed_tool_ids: list[str] = []
    for tool in registry.list_tools():
        if not isinstance(tool, dict) or not _tool_matches_server(tool, server_id):
            continue
        tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip()
        if not tool_id:
            continue
        registry.unregister(tool_id)
        removed_tool_ids.append(tool_id)

    lock = getattr(registry, "_lock", None)
    servers = getattr(registry, "_mcp_servers", None)
    if lock is not None and isinstance(servers, dict):
        with lock:
            servers.pop(server_id, None)
    return removed_tool_ids


def _run_lifecycle(input_data: Any, context: Any, *, action: str) -> dict[str, Any]:
    payload = input_data if isinstance(input_data, dict) else {}
    server_id = _server_id(payload)
    if not server_id:
        return error("'server_id' is required", code="INVALID_INPUT")

    registry = McpRegistry()
    if registry.get_server(server_id) is None:
        return error("MCP server not found: " + server_id, code="NOT_FOUND")

    operation = "tool.mcp_remove" if action == "remove" else "tool.mcp_disconnect"
    risk = "high" if action == "remove" else "medium"
    approval_input = {
        "server_id": server_id,
        "action": action,
        **(
            {"approval_token": payload.get("approval_token")}
            if payload.get("approval_token")
            else {}
        ),
    }
    record_tool_attempt(operation, risk, approval_input)
    approval = approved_or_request(approval_input, context, operation, risk)
    if approval is not None:
        return approval

    try:
        removed_tool_ids = _disconnect_runtime(server_id)
        deleted = False
        if action == "remove":
            deleted = registry.delete_server(server_id)
            if not deleted:
                raise RuntimeError("MCP server disappeared before removal completed")
        else:
            registry.mark_connected(
                server_id,
                status="disconnected",
                tools=[],
                approved=registry.is_approved(server_id),
            )
        record_tool_execution(
            operation,
            risk,
            approval_input,
            server_name=server_id,
            removed_tools=len(removed_tool_ids),
        )
        return ok(
            {
                "server_id": server_id,
                "status": "removed" if action == "remove" else "disconnected",
                "deleted": deleted,
                "removed_tools": removed_tool_ids,
            }
        )
    except Exception as exc:
        record_tool_failure(operation, risk, approval_input, str(exc), server_name=server_id)
        return error(
            "MCP {} failed: {}".format(action, exc),
            code="MCP_LIFECYCLE_ERROR",
        )


def run_disconnect(input_data: Any, context: Any = None) -> dict[str, Any]:
    return _run_lifecycle(input_data, context, action="disconnect")


def run_remove(input_data: Any, context: Any = None) -> dict[str, Any]:
    return _run_lifecycle(input_data, context, action="remove")
