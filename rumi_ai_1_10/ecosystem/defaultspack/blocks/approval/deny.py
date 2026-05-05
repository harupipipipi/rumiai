from __future__ import annotations

from ._common import ApprovalStore, approval_error, ok


def run(input_data, context=None):
    try:
        return ok(
            ApprovalStore().deny(
                str(input_data.get("approval_id") or input_data.get("id") or ""),
                reason=str(input_data.get("reason") or ""),
            )
        )
    except Exception as exc:
        return approval_error(exc)
