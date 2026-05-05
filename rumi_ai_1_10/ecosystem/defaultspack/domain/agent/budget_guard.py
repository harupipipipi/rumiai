from __future__ import annotations

from typing import Any


class BudgetGuard:
    def check(self, definition: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        stop = definition.get("stop_conditions") if isinstance(definition.get("stop_conditions"), dict) else {}
        max_cost = stop.get("max_cost_usd")
        max_tokens = stop.get("max_tokens")
        cost = float(state.get("current_cost_usd") or 0)
        tokens = int(state.get("current_tokens") or 0)
        max_runs = stop.get("max_runs")
        if max_runs is not None and int(state.get("run_count") or 0) >= int(max_runs):
            return {"allowed": False, "blocked_reason": "budget_exceeded", "metric": "runs"}
        if max_cost is not None and cost >= float(max_cost):
            return {"allowed": False, "blocked_reason": "budget_exceeded", "metric": "cost"}
        if max_tokens is not None and tokens >= int(max_tokens):
            return {"allowed": False, "blocked_reason": "token_budget_exceeded", "metric": "tokens"}
        return {"allowed": True}
