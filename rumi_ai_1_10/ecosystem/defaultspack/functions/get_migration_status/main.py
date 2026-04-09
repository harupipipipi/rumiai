from __future__ import annotations

from core_runtime.defaultspack_migration import get_defaultspack_migration_manager


def run(context, args):
    return get_defaultspack_migration_manager().status()
