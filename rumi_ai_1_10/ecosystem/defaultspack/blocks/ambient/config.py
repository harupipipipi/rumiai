from __future__ import annotations

from blocks._common import error, ok
from domain.ambient.router import AmbientTriggerRouter


def run(input_data, context=None):
    del context
    payload = input_data if isinstance(input_data, dict) else {}
    try:
        return ok(AmbientTriggerRouter().configure(payload))
    except Exception as exc:
        return error(str(exc), "AMBIENT_CONFIG_FAILED")
