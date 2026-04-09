from __future__ import annotations

from core_runtime.setup_pack import get_setup_pack_manager


def run(context, args):
    return get_setup_pack_manager().list_packs()
