from __future__ import annotations

from core_runtime.defaultspack_manager import get_defaultspack_manager
from core_runtime.di_container import get_container


def run(context, args):
    payload = dict(args or {})
    module_id = str(payload.get("module_id", "")).strip()
    state = str(payload.get("state", "")).strip()
    reason = str(payload.get("reason", "")).strip()
    if not module_id:
        return {"error": "module_id is required", "status_code": 400}
    if not state:
        return {"error": "state is required", "status_code": 400}

    container = get_container()
    event_bus = container.get_or_none("event_bus") if container is not None else None
    manager = get_defaultspack_manager(event_bus=event_bus)

    if state == "enabled" and reason == "manual_reload":
        return manager.reload(module_id)
    if state == "enabled" and reason == "manual_recover":
        return manager.recover(module_id)
    if state == "disabled" and reason == "manual_rollback":
        return manager.rollback(module_id)
    if state == "disabled":
        return manager.disable(module_id, reason=reason or "manual_disable")
    if state == "enabled":
        return manager.enable(module_id)
    return manager.set_state(module_id, state, reason=reason)
