from __future__ import annotations

from typing import Any

from .budget_guard import BudgetGuard
from .lifecycle_policy import LifecyclePolicy
from .rate_guard import RateGuard


class AgentLifecycle:
    def __init__(self) -> None:
        self.lifecycle = LifecyclePolicy()
        self.budget = BudgetGuard()
        self.rate = RateGuard()

    def before_tick(self, definition: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        for guard in (self.lifecycle, self.budget, self.rate):
            result = guard.evaluate(definition, state) if hasattr(guard, "evaluate") else guard.check(definition, state)
            if result.get("allowed") is False:
                return result
        return {"allowed": True}
