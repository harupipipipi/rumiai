from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.ui_compiler_test_utils import build_args, fake_context, write_pass_package

from domain.tool.ui_compiler_tools import ui_build_recursive


def test_compression_inspector_reports_action_pressure_and_overflow(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    args = build_args("compression-run")
    args["options"]["fakeFailures"] = {
        "reply-composer/candidate-1": "action-pressure",
        "reply-composer/candidate-2": "action-pressure",
    }

    result = ui_build_recursive(args, fake_context(tmp_path))
    report = json.loads(
        (tmp_path / ".rumi" / "ui" / "runs" / "compression-run" / "candidates" / "reply-composer" / "candidate-1" / "inspection.json")
        .read_text(encoding="utf-8")
    )

    assert result["status"] == "error"
    assert any(issue["code"] in {"ACTION_PRESSURE", "HORIZONTAL_OVERFLOW"} for issue in report["issues"])


@pytest.mark.parametrize(
    ("fail_mode", "issue_code"),
    [
        ("primary-clipped", "TEXT_PRESSURE"),
        ("tiny-font", "TINY_FONT_ESCAPE"),
        ("touch-target", "TOUCH_TARGET_TOO_SMALL"),
        ("toolbar-overflow", "RESPONSIVE_STRESS"),
        ("primary-action-unreachable", "PRIMARY_ACTION_UNREACHABLE"),
    ],
)
def test_compression_hard_gates_fail_the_candidate(tmp_path: Path, fail_mode: str, issue_code: str) -> None:
    write_pass_package(tmp_path / "project")
    run_id = f"gate-{fail_mode}"
    args = build_args(run_id)
    args["options"]["fakeFailures"] = {
        "reply-composer/candidate-1": fail_mode,
        "reply-composer/candidate-2": fail_mode,
    }

    result = ui_build_recursive(args, fake_context(tmp_path))
    report = json.loads(
        (
            tmp_path
            / ".rumi"
            / "ui"
            / "runs"
            / run_id
            / "candidates"
            / "reply-composer"
            / "candidate-1"
            / "inspection.json"
        ).read_text(encoding="utf-8")
    )

    assert result["status"] == "error"
    assert any(issue["code"] == issue_code for issue in report["issues"])


def test_compression_pressure_metrics_are_reported_without_placeholder_values(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    args = build_args("pressure-metrics")
    args["options"]["fakeFailures"] = {
        "reply-composer/candidate-1": "gap-pressure",
        "reply-composer/candidate-2": "nested-surfaces",
    }

    result = ui_build_recursive(args, fake_context(tmp_path))
    gap_report = json.loads(
        (
            tmp_path
            / ".rumi"
            / "ui"
            / "runs"
            / "pressure-metrics"
            / "candidates"
            / "reply-composer"
            / "candidate-1"
            / "inspection.json"
        ).read_text(encoding="utf-8")
    )
    surface_report = json.loads(
        (
            tmp_path
            / ".rumi"
            / "ui"
            / "runs"
            / "pressure-metrics"
            / "candidates"
            / "reply-composer"
            / "candidate-2"
            / "inspection.json"
        ).read_text(encoding="utf-8")
    )

    assert result["status"] == "ok"
    assert gap_report["metrics"]["gapPressure"] > 0
    assert any(issue["code"] == "GAP_PRESSURE" for issue in gap_report["issues"])
    assert surface_report["metrics"]["surfacePressure"] > 0
    assert any(issue["code"] == "SURFACE_PRESSURE" for issue in surface_report["issues"])


def test_valid_component_has_no_compression_failures(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    result = ui_build_recursive(build_args("comfortable-run"), fake_context(tmp_path))
    final = json.loads((tmp_path / ".rumi" / "ui" / "runs" / "comfortable-run" / "reports" / "final.json").read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    assert final["summary"]["compressionFailures"] == 0
    assert final["pageCompression"]["status"] == "pass"
