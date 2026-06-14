from __future__ import annotations

from blocks._common import error, ok
from domain.ambient.router import AmbientTriggerRouter


def run(input_data, context=None):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    permission_id = str(payload.get("permission_id") or payload.get("id") or "").strip()
    action = str(payload.get("action") or "grant").strip().lower()
    router = AmbientTriggerRouter()
    try:
        if action in {"check_os", "os_check", "update_os"}:
            statuses = payload.get("statuses")
            if isinstance(statuses, dict):
                return ok(router.check_os_permissions(statuses))
            if payload.get("os_status"):
                return ok(router.check_os_permissions({permission_id: payload.get("os_status")}))
            return error("statuses or os_status is required", "INVALID_PERMISSION_STATUS")
        if not permission_id:
            return error("permission_id is required", "INVALID_PERMISSION")
        if action == "revoke":
            return ok(router.revoke_permission(permission_id))
        return ok(router.grant_permission(permission_id, os_status=payload.get("os_status")))
    except Exception as exc:
        return error(str(exc), "AMBIENT_PERMISSION_FAILED")
