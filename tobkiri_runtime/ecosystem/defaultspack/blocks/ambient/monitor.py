from __future__ import annotations

from blocks._common import error, ok
from domain.ambient.router import AmbientTriggerRouter


def run(input_data, context=None):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    action = str(payload.get("action") or "start").strip().lower()
    router = AmbientTriggerRouter()
    try:
        if action == "stop":
            return ok(router.stop_monitor())
        return ok(router.start_monitor(payload))
    except Exception as exc:
        return error(str(exc), "AMBIENT_MONITOR_FAILED")
