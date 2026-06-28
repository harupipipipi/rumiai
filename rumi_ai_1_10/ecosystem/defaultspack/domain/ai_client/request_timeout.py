from __future__ import annotations

import math
from typing import Any


PROVIDER_REQUEST_TIMEOUT_RESERVE_SECONDS = 5.0
PROVIDER_REQUEST_TIMEOUT_MIN_SECONDS = 2.0
PROVIDER_REQUEST_TIMEOUT_MAX_SECONDS = 120.0


def provider_request_timeout_for_execution_timeout(timeout_seconds: Any) -> float | None:
    """Translate an outer execution timeout into a provider network timeout."""
    try:
        value = float(timeout_seconds)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return max(
        PROVIDER_REQUEST_TIMEOUT_MIN_SECONDS,
        min(
            PROVIDER_REQUEST_TIMEOUT_MAX_SECONDS,
            value - PROVIDER_REQUEST_TIMEOUT_RESERVE_SECONDS,
        ),
    )


def apply_execution_timeout_to_params(
    params: dict[str, Any],
    timeout_seconds: Any,
) -> dict[str, Any]:
    if "request_timeout" in params or "timeout" in params:
        return params
    request_timeout = provider_request_timeout_for_execution_timeout(timeout_seconds)
    if request_timeout is not None:
        params["request_timeout"] = request_timeout
    return params
