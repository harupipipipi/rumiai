from __future__ import annotations

from core_runtime.pack_modification_manager import get_pack_modification_manager


def run(context, args):
    payload = dict(args or {})
    status = str(payload.get("status", "all")).strip() or "all"
    return get_pack_modification_manager().list_requests(status_filter=status)
