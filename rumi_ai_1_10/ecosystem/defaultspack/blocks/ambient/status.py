from __future__ import annotations

from blocks._common import error, ok
from domain.ambient.router import AmbientTriggerRouter


def run(input_data, context=None):
    del input_data, context
    try:
        return ok(AmbientTriggerRouter().status())
    except Exception as exc:
        return error(str(exc), "AMBIENT_STATUS_FAILED")
