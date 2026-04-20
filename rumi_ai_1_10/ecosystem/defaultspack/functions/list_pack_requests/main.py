from __future__ import annotations

from ecosystem.defaultspack.backend.pack_extension.extension_manager import get_extension_manager


def run(context, args):
    payload = dict(args or {})
    status = str(payload.get("status", "all")).strip() or "all"
    return get_extension_manager().list_requests(status_filter=status)
