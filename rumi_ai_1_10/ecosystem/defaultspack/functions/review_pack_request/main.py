from __future__ import annotations

from ecosystem.defaultspack.backend.pack_extension.extension_manager import get_extension_manager


def run(context, args):
    payload = dict(args or {})
    request_id = str(payload.get("request_id", "")).strip()
    decision = str(payload.get("decision", "")).strip()
    notes = str(payload.get("decision_notes", "")).strip()
    if not request_id:
        return {"error": "request_id is required", "status_code": 400}
    if decision == "approve":
        return get_extension_manager().approve_request(
            request_id=request_id,
            reviewer=str(context.get("pack_id", "defaultspack")),
            decision_notes=notes,
        )
    if decision == "reject":
        return get_extension_manager().reject_request(
            request_id=request_id,
            reviewer=str(context.get("pack_id", "defaultspack")),
            reason=notes,
        )
    return {"error": f"Unsupported decision: {decision}", "status_code": 400}
