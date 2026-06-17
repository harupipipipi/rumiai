from __future__ import annotations

from blocks._common import ok
from domain.ambient.router import AmbientTriggerRouter


def run(input_data, context=None):
    payload = input_data if isinstance(input_data, dict) else {}
    action = str(payload.get("action") or "approve").strip().lower()
    request_id = str(payload.get("request_id") or payload.get("approval_request_id") or "").strip()
    router = AmbientTriggerRouter()
    if action in {"deny", "reject", "cancel"}:
        return ok(router.deny_pending(request_id, reason=str(payload.get("reason") or "")))
    return ok(router.approve_pending(request_id, context or {}))
