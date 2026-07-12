from __future__ import annotations

from core_runtime.di_container import get_container
from ecosystem.defaultspack.backend.module_state import get_module_state_manager


def run(context, args):
    module_id = str((args or {}).get("module_id", "")).strip()
    if not module_id:
        return {"error": "module_id is required", "status_code": 400}

    container = get_container()
    event_bus = container.get_or_none("event_bus") if container is not None else None
    module = get_module_state_manager(event_bus=event_bus).get_module(module_id)
    if module is None:
        return {"error": f"Unknown module: {module_id}", "status_code": 404}
    return module
