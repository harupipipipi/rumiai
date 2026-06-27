from __future__ import annotations

import json
from pathlib import Path

from tests.ui_compiler_test_utils import build_args, fake_context, fixture_tree, write_pass_package

from domain.tool.ui_compiler_tools import ui_build_recursive
from domain.tool_policy.internal_context import mark_tool_server_approval_context
from domain.ui_compiler import RecursiveUIPlanner


def test_build_recursive_rejects_without_internal_approval_and_workspace(tmp_path: Path) -> None:
    raw_yolo = ui_build_recursive(
        build_args("raw-yolo"),
        {"profile_policy": {"yolo_mode": True}, "conversation_workspace_dir": str(tmp_path)},
    )
    no_workspace = ui_build_recursive(build_args("no-workspace"), mark_tool_server_approval_context({}))

    assert raw_yolo["status"] == "error"
    assert raw_yolo["error"]["code"] == "APPROVAL_REQUIRED"
    assert no_workspace["status"] == "error"


def test_build_recursive_creates_run_bundle_tasks_and_candidates(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    result = ui_build_recursive(build_args("runtime-run"), fake_context(tmp_path))

    run_root = tmp_path / ".rumi" / "ui" / "runs" / "runtime-run"
    task_files = sorted((run_root / "agent-tasks").glob("*.json"))

    assert result["status"] == "ok"
    assert result["data"]["summary"]["foundationCandidates"] == 3
    assert result["data"]["summary"]["contracts"] == 3
    assert result["data"]["summary"]["candidateBundles"] == 5
    assert (run_root / "foundation" / "accepted" / "foundation.json").is_file()
    assert (run_root / "reports" / "final.json").is_file()
    assert len(task_files) == 8
    assert all("outputDir" in json.loads(path.read_text(encoding="utf-8")) for path in task_files)


def test_candidate_count_output_dirs_are_isolated_and_do_not_include_previous_source(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    ui_build_recursive(build_args("isolation-run"), fake_context(tmp_path))
    run_root = tmp_path / ".rumi" / "ui" / "runs" / "isolation-run"
    composer_tasks = sorted((run_root / "agent-tasks").glob("*reply-composer-candidate-*.json"))

    assert len(composer_tasks) == 2
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in composer_tasks]
    assert len({payload["outputDir"] for payload in payloads}) == 2
    assert all("previous candidate" not in payload["prompt"].lower() for payload in payloads)


def test_failed_candidate_is_not_accepted_and_all_failed_node_fails_run(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    partial = build_args("selector-run")
    partial["options"]["fakeFailures"] = {"reply-composer/candidate-1": "action-pressure"}
    partial_result = ui_build_recursive(partial, fake_context(tmp_path))
    selection = json.loads(
        (tmp_path / ".rumi" / "ui" / "runs" / "selector-run" / "accepted" / "reply-composer" / "selection.json")
        .read_text(encoding="utf-8")
    )

    all_failed = build_args("selector-fail")
    all_failed["options"]["fakeFailures"] = {
        "reply-composer/candidate-1": "action-pressure",
        "reply-composer/candidate-2": "action-pressure",
    }
    failed_result = ui_build_recursive(all_failed, fake_context(tmp_path))

    assert partial_result["status"] == "ok"
    assert selection["acceptedCandidateId"] == "candidate-2"
    assert any(item["candidateId"] == "candidate-1" for item in selection["rejected"])
    assert failed_result["status"] == "error"
    assert failed_result["error"]["code"] == "UI_RECURSIVE_BUILD_FAILED"


def test_rerun_with_same_idempotency_key_returns_existing_final_report(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    args = build_args("idempotent-run")
    args["idempotency_key"] = "same-request"

    first = ui_build_recursive(args, fake_context(tmp_path))
    second = ui_build_recursive(args, fake_context(tmp_path))

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["data"]["idempotent"] is True
    assert second["data"]["summary"] == first["data"]["summary"]


def test_calendar_fixture_contains_required_recursive_calendar_responsibilities() -> None:
    plan = RecursiveUIPlanner().plan(fixture_tree("calendar_contract"), run_id="calendar-fixture")
    contract_ids = {contract.id for contract in plan.contracts()}

    assert plan.is_executable()
    assert {"week-grid", "time-axis", "event-block", "mobile-agenda", "event-editor"}.issubset(contract_ids)
