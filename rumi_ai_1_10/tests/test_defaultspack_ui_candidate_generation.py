from __future__ import annotations

import json
from pathlib import Path

from tests.ui_compiler_test_utils import build_args, fake_context, write_pass_package

from domain.tool.ui_compiler_tools import ui_build_recursive


def test_leaf_candidate_bundles_include_design_intent_and_fixtures(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    ui_build_recursive(build_args("candidate-run"), fake_context(tmp_path))
    candidate = tmp_path / ".rumi" / "ui" / "runs" / "candidate-run" / "candidates" / "reply-composer" / "candidate-1"
    manifest = json.loads((candidate / "component.manifest.json").read_text(encoding="utf-8"))

    assert (candidate / "design-intent.json").is_file()
    assert (candidate / "source" / "Component.tsx").is_file()
    assert (candidate / "source" / "Component.module.css").is_file()
    assert {path.name for path in (candidate / "fixtures").glob("*.json")} == {
        "default.json",
        "long.json",
        "empty.json",
        "loading.json",
        "error.json",
    }
    assert manifest["designIntent"]["compressionAvoidancePlan"]


def test_missing_design_intent_and_non_token_color_fail_validation(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    bad_state = build_args("missing-state-run")
    bad_state["options"]["fakeFailures"] = {
        "reply-composer/candidate-1": "missing-state",
        "reply-composer/candidate-2": "missing-state",
        "reply-composer/candidate-retry-1": "missing-state",
    }
    bad_color = build_args("non-token-run")
    bad_color["options"]["fakeFailures"] = {
        "reply-composer/candidate-1": "non-token-color",
        "reply-composer/candidate-2": "non-token-color",
        "reply-composer/candidate-retry-1": "non-token-color",
    }

    state_result = ui_build_recursive(bad_state, fake_context(tmp_path))
    color_result = ui_build_recursive(bad_color, fake_context(tmp_path))

    assert state_result["status"] == "error"
    assert color_result["status"] == "error"
    color_report = json.loads(
        (tmp_path / ".rumi" / "ui" / "runs" / "non-token-run" / "candidates" / "reply-composer" / "candidate-1" / "inspection.json")
        .read_text(encoding="utf-8")
    )
    assert any(issue["code"] == "NON_TOKEN_COLOR" for issue in color_report["issues"])
