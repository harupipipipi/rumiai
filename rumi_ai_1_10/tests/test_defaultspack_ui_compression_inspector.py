from __future__ import annotations

import json
from pathlib import Path

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


def test_valid_component_has_no_compression_failures(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    result = ui_build_recursive(build_args("comfortable-run"), fake_context(tmp_path))
    final = json.loads((tmp_path / ".rumi" / "ui" / "runs" / "comfortable-run" / "reports" / "final.json").read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    assert final["summary"]["compressionFailures"] == 0
    assert final["pageCompression"]["status"] == "pass"
