from __future__ import annotations

from ._common import ApprovalStore, approval_error, ok


def run(input_data, context=None):
    try:
        return ok(
            {
                "approvals": ApprovalStore().list(
                    include_expired=bool(input_data.get("include_expired")),
                    status=str(input_data.get("status") or ""),
                )
            }
        )
    except Exception as exc:
        return approval_error(exc)
