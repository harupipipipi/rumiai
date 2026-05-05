from __future__ import annotations

from typing import Any
from datetime import datetime, timezone


def _parse_timestamp(value: Any):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class RateGuard:
    def check(self, definition: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        runtime = definition.get("runtime_policy") if isinstance(definition.get("runtime_policy"), dict) else {}
        max_parallel = int(runtime.get("max_concurrent_children") or 1)
        current = int(state.get("current_parallel_runs") or 0)
        if current >= max_parallel:
            return {"allowed": False, "blocked_reason": "rate_limited", "metric": "parallel_runs"}
        min_seconds = runtime.get("min_seconds_between_ticks")
        last_tick = _parse_timestamp(state.get("last_tick_at"))
        if min_seconds is not None and last_tick is not None:
            elapsed = (datetime.now(timezone.utc) - last_tick).total_seconds()
            if elapsed < float(min_seconds):
                return {"allowed": False, "blocked_reason": "rate_limited", "metric": "min_seconds_between_ticks"}
        return {"allowed": True}
