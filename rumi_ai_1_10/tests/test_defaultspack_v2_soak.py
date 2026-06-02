from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_soak_task_queue_can_resume(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    runner = SoakTestRunner(runtime, state_path=tmp_path / "soak.json")
    tasks = runner.load_task_queue()
    assert len(tasks) >= 10

    runner.save_task_queue(tasks[:3])
    assert runner.can_resume() is True

    remaining = runner.load_task_queue()
    assert len(remaining) == 3


def test_soak_records_hourly_summary(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    runner = SoakTestRunner(runtime, state_path=tmp_path / "soak.json")
    runner.record_hourly_summary({"completed": 3, "failed": 1, "hour": 1})
    runner.record_hourly_summary({"completed": 5, "failed": 1, "hour": 2})

    state = json.loads((tmp_path / "soak.json").read_text(encoding="utf-8"))
    assert len(state["hourly_summaries"]) == 2
    assert state["hourly_summaries"][0]["summary"]["hour"] == 1


def test_soak_final_report_contains_failures_and_friction(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    runner = SoakTestRunner(runtime, state_path=tmp_path / "soak.json")
    runner.record_task_result(
        "soak_01",
        status="completed",
        model_role="main",
        model_id="mimo-v2.5-pro",
        tools_used=["coding_file_read"],
    )
    runner.record_task_result(
        "soak_02",
        status="failed",
        model_role="main",
        model_id="mimo-v2.5-pro",
        failures=["timeout"],
        user_friction="tool call timed out after 30s",
    )

    report = runner.generate_final_report()
    assert report["total_tasks"] == 2
    assert report["completed"] == 1
    assert report["failed"] == 1
    assert len(report["friction_points"]) == 1
    assert "timed out" in report["friction_points"][0]["friction"]


def test_soak_task_definitions_are_complete():
    from domain.agent.soak_test_runner import SOAK_TASK_DEFINITIONS

    categories = {t["category"] for t in SOAK_TASK_DEFINITIONS}
    assert "coding" in categories
    assert "vision" in categories or "browser" in categories
    assert "research" in categories

    for task in SOAK_TASK_DEFINITIONS:
        assert task["task_id"]
        assert task["title"]
        assert task["expected_outcome"]
        assert isinstance(task["tools_used"], list)
