from __future__ import annotations

from core_runtime.setup_pack import get_setup_pack_manager
from ecosystem.defaultspack.backend.migration.migrator import get_defaults_migrator


def run(context, args):
    setup_pack_id = str((args or {}).get("setup_pack_id", "")).strip()
    if not setup_pack_id:
        return {"error": "setup_pack_id is required", "status_code": 400}

    manager = get_setup_pack_manager()
    result = manager.install(setup_pack_id)
    if "error" in result:
        return result

    migration = get_defaults_migrator()
    status = migration.status()
    migration_result = None
    if status.get("needs_user_migration"):
        migration_result = migration.migrate_all()

    result["migration_status"] = migration.status()
    if migration_result is not None:
        result["migration"] = migration_result
    return result
