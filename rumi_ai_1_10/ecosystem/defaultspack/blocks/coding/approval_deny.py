"""Deny a pending local coding operation."""

from blocks._common import error, ok
from domain.safety.approval import deny
from domain.safety.audit import record_approval


def run(input_data, context=None):
    request_id = str(input_data.get("approval_request_id") or input_data.get("request_id") or "").strip()
    if not request_id:
        return error("'approval_request_id' is required", code="INVALID_INPUT")
    decision = deny(request_id, str(input_data.get("reason") or ""))
    record_approval("coding.approval", request_id, "denied")
    return ok(decision)
