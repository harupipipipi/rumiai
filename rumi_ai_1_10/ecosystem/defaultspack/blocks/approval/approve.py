from __future__ import annotations

from ._common import ApprovalStore, approval_error, ok


def run(input_data, context=None):
    data = dict(input_data or {})
    scope = str(data.get("scope") or data.get("mode") or "once")
    if scope == "approve_once":
        scope = "once"
    if scope in {"approve_session", "for_session"}:
        scope = "session"
    ttl = data.get("ttl_seconds")
    try:
        approval_id = str(data.get("approval_id") or data.get("id") or "")
        store = ApprovalStore()
        ttl_seconds = int(ttl) if ttl is not None else None
        if scope == "session":
            return ok(
                store.approve_session(
                    approval_id,
                    session_id=str(data.get("session_id") or ""),
                    **({"ttl_seconds": ttl_seconds} if ttl_seconds is not None else {}),
                )
            )
        return ok(store.approve_once(approval_id, **({"ttl_seconds": ttl_seconds} if ttl_seconds is not None else {})))
    except Exception as exc:
        return approval_error(exc)
