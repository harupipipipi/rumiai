from __future__ import annotations

from typing import Any

try:
    from blocks._common import error, ok
except ModuleNotFoundError:
    from ecosystem.defaultspack.blocks._common import error, ok

from ecosystem.defaultspack.backend.continuity import ContinuityCoordinator
from ecosystem.defaultspack.backend.continuity.errors import ContinuityError


_COORDINATOR: ContinuityCoordinator | None = None


def _sandbox_manager():
    try:
        from ecosystem.defaultspack.blocks.sandbox.api import _service

        return _service().manager
    except Exception:
        return None


def _coordinator() -> ContinuityCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = ContinuityCoordinator(sandbox_manager=_sandbox_manager())
    return _COORDINATOR


def _reset_for_tests(coordinator: ContinuityCoordinator | None = None) -> None:
    global _COORDINATOR
    _COORDINATOR = coordinator


def run(input_data: dict[str, Any] | None, context: dict[str, Any] | None = None):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    method = str(payload.get("_method") or "GET").upper()
    handler = str(payload.get("_handler") or "").strip()
    if not handler:
        handler = _handler_from_method(method, payload)
    coordinator = _coordinator()
    try:
        if handler == "nodes_list":
            return ok(coordinator.list_nodes())
        if handler == "pairing_start":
            return ok(coordinator.start_pairing(payload))
        if handler == "pairing_accept":
            return ok(coordinator.accept_pairing(payload))
        if handler == "node_delete":
            return ok(coordinator.remove_node(str(payload.get("node_id") or "")))
        if handler == "node_probe":
            return ok(coordinator.probe_node(str(payload.get("node_id") or ""), payload))
        if handler == "provider_routes":
            return ok(coordinator.list_provider_routes())
        if handler == "provider_route_probe":
            return ok(coordinator.probe_provider_route(payload))
        if handler == "provider_route_set_fallbacks":
            return ok(coordinator.set_provider_fallbacks(payload))
        if handler == "provider_extensions":
            return ok(coordinator.list_provider_extensions())
        if handler == "plan":
            return ok(coordinator.plan_handoff(payload))
        if handler == "handoff":
            return ok(coordinator.start_handoff(payload))
        if handler == "handoff_get":
            return ok({"operation": coordinator.get_operation(str(payload.get("operation_id") or ""))})
        if handler == "handoffs_list":
            return ok(coordinator.list_operations())
        if handler == "handoff_cancel":
            return ok(coordinator.cancel(str(payload.get("operation_id") or "")))
        if handler == "handoff_retry":
            return ok(coordinator.retry(str(payload.get("operation_id") or "")))
        if handler == "handoff_return":
            return ok(coordinator.return_to_device(str(payload.get("operation_id") or "")))
        if handler == "checkpoint":
            return ok(coordinator.checkpoint(payload))
    except ContinuityError as exc:
        return {
            "status": "error",
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "_http_status": exc.status_code,
        }
    return error(f"Unknown continuity handler: {handler}", "UNKNOWN_CONTINUITY_HANDLER")


def _handler_from_method(method: str, payload: dict[str, Any]) -> str:
    operation_id = str(payload.get("operation_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    route_id = str(payload.get("route_id") or "").strip()
    if method == "GET" and not operation_id and not node_id and not route_id:
        return "nodes_list"
    return ""
