from __future__ import annotations

from ecosystem.defaultspack.backend.pack_extension.extension_manager import get_extension_manager


def run(context, args):
    payload = dict(args or {})
    return get_extension_manager().create_pack_request(
        mode="forced_patch",
        staging_id=str(payload.get("staging_id", "")).strip(),
        actor=str(context.get("pack_id", "defaultspack")),
        notes=str(payload.get("notes", "")).strip(),
        target_pack_id=str(payload.get("target_pack_id", "")).strip(),
        slot=str(payload.get("slot", "default")).strip() or "default",
        fullscreen=bool(payload.get("fullscreen", False)),
        exclusive=bool(payload.get("exclusive", False)),
    )
