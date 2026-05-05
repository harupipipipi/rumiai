from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_budget_guard_denies_run_budget():
    from domain.agent.budget_guard import BudgetGuard

    result = BudgetGuard().check({"stop_conditions": {"max_runs": 1}}, {"run_count": 1})
    assert result["allowed"] is False
    assert result["metric"] == "runs"
