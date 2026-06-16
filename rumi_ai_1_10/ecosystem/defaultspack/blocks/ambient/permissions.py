from __future__ import annotations

from blocks._common import error, ok
from domain.ambient.router import AmbientTriggerRouter


AMBIENT_AUTHORITY_REQUEST_ID = "rumi_ambient_trigger_pack"


def _verify_ambient_operator(ui_operator):
    from core_runtime.authority.ui_operator import ui_operator_audit_record, verify_ui_operator

    operator_ok, operator_error, operator_payload = verify_ui_operator(
        ui_operator,
        request_id=AMBIENT_AUTHORITY_REQUEST_ID,
    )
    if not operator_ok:
        return False, operator_error, {}
    return True, "", ui_operator_audit_record(operator_payload)


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
        operator_ok, operator_error, audit = _verify_ambient_operator(payload.get("ui_operator"))
        if not operator_ok:
            return error(operator_error, "AMBIENT_PERMISSION_UI_OPERATOR_REQUIRED")
        if action == "revoke":
            state = router.revoke_permission(permission_id)
        else:
            state = router.grant_permission(permission_id, os_status=payload.get("os_status"))
        state["authority"] = {"request_id": AMBIENT_AUTHORITY_REQUEST_ID, **audit}
        return ok(state)
    except Exception as exc:
        return error(str(exc), "AMBIENT_PERMISSION_FAILED")
