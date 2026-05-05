from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_lifecycle_policy_reports_stop_conditions():
    from domain.agent.lifecycle_policy import AgentLifecyclePolicy, LifecyclePolicy

    definition = {"enabled": True, "stop_conditions": {"max_failures": 2}}
    assert LifecyclePolicy().evaluate(definition, {"failure_count": 1})["allowed"] is True
    blocked = LifecyclePolicy().evaluate(definition, {"failure_count": 2})
    assert blocked["allowed"] is False
    assert AgentLifecyclePolicy().evaluate_stop_conditions(definition, {"failure_count": 2})[0]["code"] == "max_failures"
