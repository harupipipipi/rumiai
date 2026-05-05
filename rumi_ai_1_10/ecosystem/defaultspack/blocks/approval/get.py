from __future__ import annotations

from ._common import ApprovalStore, approval_error, ok


def run(input_data, context=None):
    try:
        approval = ApprovalStore().get(str(input_data.get("approval_id") or input_data.get("id") or ""))
        if not approval:
            raise ValueError("approval not found")
        return ok(approval)
    except Exception as exc:
        return approval_error(exc)
