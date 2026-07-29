"""Approve a pending local coding operation."""

from blocks._common import error, ok
from domain.safety.approval import approve
from domain.safety.audit import record_approval
from domain.safety.debug_cli_operator import DebugCliOperatorError, verify_debug_cli_decision
from domain.tool_policy.internal_context import tool_server_approval_context_is_internal


def run(input_data, context=None):
    request_id = str(input_data.get("approval_request_id") or input_data.get("request_id") or "").strip()
    if not request_id:
        return error("'approval_request_id' is required", code="INVALID_INPUT")
    operator = input_data.get("debug_cli_operator")
    if operator is not None:
        try:
            verify_debug_cli_decision(
                request_id,
                str(input_data.get("expected_digest") or "").strip(),
                operator,
            )
        except DebugCliOperatorError as exc:
            result = error(str(exc), code="DEBUG_CLI_OPERATOR_INVALID")
            result["_http_status"] = 403
            return result
    elif not (
        isinstance(context, dict)
        and context.get("source") == "defaultspack_local_ui"
        and tool_server_approval_context_is_internal(context)
    ):
        result = error(
            "Launcher debug operator or interactive local UI provenance is required",
            code="APPROVAL_OPERATOR_REQUIRED",
        )
        result["_http_status"] = 403
        return result
    decision = approve(request_id)
    record_approval(
        "coding.approval",
        request_id,
        "approved" if decision.get("approved") else "failed",
        decision_source="delegated_debug_cli" if operator is not None else "interactive_local_ui",
        human_approved=False if operator is not None else True,
    )
    if not decision.get("approved"):
        result = error(str(decision.get("reason") or "approval failed"), code="APPROVAL_FAILED")
        result["_http_status"] = 403
        return result
    return ok(decision)
