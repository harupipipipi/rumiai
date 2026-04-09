from __future__ import annotations

from core_runtime.setup_pack import get_setup_pack_manager


def run(context, args):
    setup_pack_id = str((args or {}).get("setup_pack_id", "")).strip()
    if not setup_pack_id:
        return {"error": "setup_pack_id is required", "status_code": 400}
    return get_setup_pack_manager().revoke_all_ok(setup_pack_id)
