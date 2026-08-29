from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
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
    assert state["heartbeat_count"] == 2
    assert state["last_heartbeat_at"]


def test_soak_claims_tasks_with_lease_and_consumes_completed_queue(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    runner = SoakTestRunner(runtime, state_path=tmp_path / "soak.json")
    tasks = runner.load_task_queue()[:2]
    runner.save_task_queue(tasks)

    claimed = runner.claim_next_task(lease_seconds=30, now_epoch=1000)
    assert claimed is not None
    assert claimed["task_id"] == tasks[0]["task_id"]
    assert claimed["lease_expires_epoch"] == 1030

    runner.record_task_result(
        claimed["task_id"],
        status="completed",
        tools_used=["coding_file_read"],
    )

    state = json.loads((tmp_path / "soak.json").read_text(encoding="utf-8"))
    assert state["active_task"] is None
    assert [task["task_id"] for task in state["task_queue"]] == [tasks[1]["task_id"]]


def test_soak_reclaims_expired_task_with_incremented_attempt(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    runner = SoakTestRunner(runtime, state_path=tmp_path / "soak.json")
    runner.save_task_queue(runner.load_task_queue()[:1])

    first = runner.claim_next_task(lease_seconds=30, now_epoch=1000)
    second = runner.claim_next_task(lease_seconds=30, now_epoch=1031)

    state = json.loads((tmp_path / "soak.json").read_text(encoding="utf-8"))

    assert first is not None
    assert second is not None
    assert first["attempt"] == 1
    assert second["attempt"] == 2
    assert state["task_queue"][0]["attempt"] == 2
    assert state["active_task"]["attempt"] == 2
    assert state["lease_events"][0]["kind"] == "lease_expired"


def test_soak_claimed_dogfood_records_active_lease_during_task(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    state_path = tmp_path / "soak.json"
    runner = SoakTestRunner(runtime, state_path=state_path)
    runner.start_run()
    tasks = runner.load_task_queue()[:2]
    runner.save_task_queue(tasks)
    active_seen: list[tuple[str, str, int]] = []

    def fake_task_runner(**kwargs):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        active = state["active_task"]
        active_seen.append(
            (
                kwargs["task_id"],
                active["task_id"],
                int(active["lease_expires_epoch"] - active["started_at_epoch"]),
            )
        )
        return {
            "success": True,
            "task_id": kwargs["task_id"],
            "model": "fake/model",
            "files_read": ["math_utils.py"],
            "files_modified": ["math_utils.py"],
            "test_exit_code": 0,
        }

    result = runner.run_claimed_dogfood_tasks(
        workspace_root=tmp_path,
        task_count=2,
        lease_seconds=30,
        task_runner=fake_task_runner,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["successful"] == 2
    assert [r["claimed_task_id"] for r in result["results"]] == [t["task_id"] for t in tasks]
    assert active_seen == [(t["task_id"], t["task_id"], 30) for t in tasks]
    assert state["active_task"] is None
    assert state["task_queue"] == []
    assert [r["task_id"] for r in state["results"]] == [t["task_id"] for t in tasks]
    assert state["results"][0]["tools_used"] == tasks[0]["tools_used"]


def test_soak_claimed_dogfood_leaves_active_lease_for_recovery_on_process_exit(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    state_path = tmp_path / "soak.json"
    runner = SoakTestRunner(runtime, state_path=state_path)
    runner.start_run()
    runner.save_task_queue(runner.load_task_queue()[:1])

    def crashing_task_runner(**kwargs):
        raise SystemExit(f"simulated process exit during {kwargs['task_id']}")

    with pytest.raises(SystemExit):
        runner.run_claimed_dogfood_tasks(
            workspace_root=tmp_path,
            task_count=1,
            lease_seconds=30,
            task_runner=crashing_task_runner,
        )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    active = state["active_task"]
    assert active["task_id"] == state["task_queue"][0]["task_id"]
    assert state["results"] == []

    health = runner.health_status(now_epoch=active["lease_expires_epoch"] + 1)
    assert health["active_task"] == active["task_id"]
    assert "active task lease expired" in health["reasons"]

    reclaimed = runner.claim_next_task(
        lease_seconds=30,
        now_epoch=active["lease_expires_epoch"] + 1,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert reclaimed is not None
    assert reclaimed["task_id"] == active["task_id"]
    assert reclaimed["attempt"] == 2
    assert state["lease_events"][0]["kind"] == "lease_expired"


def test_soak_default_runner_forces_dry_run_without_live_opt_in(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    state_path = tmp_path / "soak.json"
    runner = SoakTestRunner(runtime, state_path=state_path)
    runner.start_run()
    runner.save_task_queue(runner.load_task_queue()[:1])

    result = runner.run_claimed_dogfood_tasks(workspace_root=tmp_path, task_count=1)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["dry_run"] is True
    assert result["results"][0]["dry_run"] is True
    assert result["results"][0]["dry_run_reason"] == "live privileged soak execution was not explicitly enabled"
    assert state["results"][0]["status"] == "skipped"
    assert state["results"][0]["files_modified"] == []


def test_soak_live_policy_requires_ci_allowed_root_and_approval(tmp_path, monkeypatch):
    from domain.agent.soak_test_runner import LIVE_PRIVILEGED_OPT_IN_ENV, _live_execution_policy

    workspace = tmp_path / "allowed" / "workspace"
    workspace.mkdir(parents=True)
    approval_context = {
        "_tool_server_approved": True,
        "_tool_server_approval_token_valid": True,
    }

    monkeypatch.delenv(LIVE_PRIVILEGED_OPT_IN_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert _live_execution_policy(
        workspace,
        allow_live_execution=True,
        allowed_workspace_root=tmp_path / "allowed",
        approval_context=approval_context,
    )["allowed"] is False

    monkeypatch.setenv(LIVE_PRIVILEGED_OPT_IN_ENV, "true")
    assert _live_execution_policy(
        workspace,
        allow_live_execution=True,
        allowed_workspace_root=tmp_path / "allowed",
        approval_context=approval_context,
    )["reason"] == "live privileged soak execution is CI-only"

    monkeypatch.setenv("CI", "true")
    assert _live_execution_policy(
        workspace,
        allow_live_execution=True,
        allowed_workspace_root=tmp_path / "other",
        approval_context=approval_context,
    )["reason"] == "workspace is outside the allowed live soak root"

    assert _live_execution_policy(
        workspace,
        allow_live_execution=True,
        allowed_workspace_root=tmp_path / "allowed",
        approval_context={},
    )["reason"] == "live privileged soak execution requires a server approval context"

    assert _live_execution_policy(
        workspace,
        allow_live_execution=True,
        allowed_workspace_root=tmp_path / "allowed",
        approval_context=approval_context,
    )["allowed"] is True


def test_soak_health_detects_stale_heartbeat_and_failed_run(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    runner = SoakTestRunner(
        runtime,
        state_path=tmp_path / "soak.json",
        heartbeat_interval_seconds=10,
        stale_after_seconds=30,
    )
    runner.start_run()
    runner.record_heartbeat({"cycle": 1})
    for idx in range(3):
        runner.record_task_result(
            f"task_{idx}",
            status="failed",
            failures=["model unavailable"],
            user_friction="model unavailable",
        )

    health = runner.health_status(now_epoch=10_000_000_000)

    assert health["status"] == "down"
    assert any("heartbeat" in reason for reason in health["reasons"])
    assert any("completed" in reason for reason in health["reasons"])


def test_soak_health_marks_all_failed_results_degraded_before_three_attempts(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    runner = SoakTestRunner(runtime, state_path=tmp_path / "soak.json")
    runner.start_run()
    runner.record_task_result(
        "task_1",
        status="failed",
        failures=["tool timeout"],
        user_friction="tool timeout",
    )

    health = runner.health_status()

    assert health["status"] == "degraded"
    assert any("all recorded tasks failed" in reason for reason in health["reasons"])


def test_soak_records_competitor_comparison_in_final_report(tmp_path):
    from domain.agent.self_improvement_runtime import create_mimo_profile
    from domain.agent.soak_test_runner import SoakTestRunner

    runtime = create_mimo_profile(workspace_root=tmp_path, state_path=tmp_path / "si.json")
    runtime.bootstrap()

    runner = SoakTestRunner(runtime, state_path=tmp_path / "soak.json")
    runner.record_competitor_comparison(
        name="OpenClaw",
        version="2026.5.28",
        verified_with=["npm view openclaw version", "npm pack openclaw@latest"],
        strengths=["heartbeat workspace"],
        gaps_for_rumi=["task lease recovery"],
    )

    report = runner.generate_final_report()

    assert report["competitor_comparisons"][0]["name"] == "OpenClaw"
    assert "task lease recovery" in report["competitor_comparisons"][0]["gaps_for_rumi"]


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


def test_defaultspack_soak_workflow_uses_claimed_dogfood_runner():
    workflow = (REPO_ROOT / ".github" / "workflows" / "defaultspack-v2-soak.yml").read_text(
        encoding="utf-8"
    )

    assert "runner.run_claimed_dogfood_tasks" in workflow
    assert "run_multi_task_dogfood" not in workflow
    assert "runner.record_task_result(" not in workflow
    assert "live_execution" in workflow
    assert "dry_run=not live_execution" in workflow
    assert "RUMI_SOAK_ALLOW_LIVE_PRIVILEGED" in workflow
