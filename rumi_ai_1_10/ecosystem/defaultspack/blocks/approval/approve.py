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
        return ok(
            ApprovalStore().approve(
                str(data.get("approval_id") or data.get("id") or ""),
                scope=scope,
                session_id=str(data.get("session_id") or ""),
                ttl_seconds=int(ttl) if ttl is not None else None,
            )
        )
    except Exception as exc:
        return approval_error(exc)
