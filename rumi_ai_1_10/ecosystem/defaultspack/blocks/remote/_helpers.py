from __future__ import annotations

from typing import Any, Callable

from blocks._common import error, ok
from domain.remote.task_gateway import RemoteTaskGatewayError


def run_gateway(call: Callable[[], dict[str, Any]]):
    try:
        return ok(call())
    except RemoteTaskGatewayError as exc:
        return error(str(exc), exc.code)
    except Exception as exc:
        return error("remote task gateway failed: " + str(exc), "REMOTE_GATEWAY_ERROR")
