from __future__ import annotations

from blocks._common import error, ok
from domain.ambient.router import AmbientTriggerRouter


def run(input_data, context=None):
    payload = input_data if isinstance(input_data, dict) else {}
    try:
        return ok(AmbientTriggerRouter().submit_event(payload, context or {}))
    except ValueError as exc:
        return error(str(exc), "INVALID_AMBIENT_EVENT")
    except Exception as exc:
        return error(str(exc), "AMBIENT_EVENT_FAILED")
