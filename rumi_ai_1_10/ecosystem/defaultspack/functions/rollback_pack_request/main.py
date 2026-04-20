from __future__ import annotations

from ecosystem.defaultspack.backend.pack_extension.extension_manager import get_extension_manager


def run(context, args):
    request_id = str((args or {}).get("request_id", "")).strip()
    if not request_id:
        return {"error": "request_id is required", "status_code": 400}
    return get_extension_manager().rollback_request(
        request_id=request_id,
        reviewer=str(context.get("pack_id", "defaultspack")),
    )
