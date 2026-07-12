"""Approve a pending local coding operation."""

from blocks._common import error, ok
from domain.safety.approval import approve
from domain.safety.audit import record_approval


def run(input_data, context=None):
    request_id = str(input_data.get("approval_request_id") or input_data.get("request_id") or "").strip()
    if not request_id:
        return error("'approval_request_id' is required", code="INVALID_INPUT")
    decision = approve(request_id)
    record_approval("coding.approval", request_id, "approved" if decision.get("approved") else "failed")
    if not decision.get("approved"):
        result = error(str(decision.get("reason") or "approval failed"), code="APPROVAL_FAILED")
        result["_http_status"] = 403
        return result
    return ok(decision)
