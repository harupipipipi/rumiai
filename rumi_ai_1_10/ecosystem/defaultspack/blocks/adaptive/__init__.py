from __future__ import annotations

from domain.adaptive.service import dispatch
from domain.function_runtime.registry import default_args_for


def run(args, context=None):
    payload = dict(args or {})
    ctx = dict(context or {})
    function_id = str(ctx.get("function_id") or "")
    route_defaults = default_args_for(function_id) if function_id else {}
    route_operation = str(route_defaults.get("operation") or "").strip()
    client_operation = str(payload.get("operation") or "").strip()
    if route_operation:
        if (
            function_id == "adaptive_prepared_action_prepare"
            and client_operation
            and client_operation != route_operation
            and not payload.get("action_type")
        ):
            payload["action_type"] = client_operation
        payload["operation"] = route_operation
    operation = str(payload.get("operation") or "")
    return dispatch(operation, payload, ctx)
