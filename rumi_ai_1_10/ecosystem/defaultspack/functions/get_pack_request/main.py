from __future__ import annotations

from core_runtime.pack_modification_manager import get_pack_modification_manager


def run(context, args):
    request_id = str((args or {}).get("request_id", "")).strip()
    if not request_id:
        return {"error": "request_id is required", "status_code": 400}
    return get_pack_modification_manager().get_request(request_id)
