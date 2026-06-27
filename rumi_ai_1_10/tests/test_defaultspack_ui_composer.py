from __future__ import annotations

import json
from pathlib import Path

from tests.ui_compiler_test_utils import build_args, fake_context, write_pass_package

from domain.tool.ui_compiler_tools import ui_build_recursive


def test_composer_connects_slot_mappings_without_editing_leaf_source(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    result = ui_build_recursive(build_args("composer-run"), fake_context(tmp_path))
    run_root = tmp_path / ".rumi" / "ui" / "runs" / "composer-run"
    composition = json.loads((run_root / "composition" / "page.manifest.json").read_text(encoding="utf-8"))
    report = json.loads((run_root / "composition" / "report.json").read_text(encoding="utf-8"))
    source_before = (run_root / "accepted" / "reply-composer" / "source" / "Component.tsx").read_text(encoding="utf-8")

    assert result["status"] == "ok"
    assert {"slotId": "reply-composer", "nodeId": "reply-composer", "parentNodeId": "inbox-page-frame"} in composition["slotMappings"]
    assert report["leafSourceEdited"] is False
    assert source_before == (run_root / "accepted" / "reply-composer" / "source" / "Component.tsx").read_text(encoding="utf-8")
    assert "reply-composer" in (run_root / "composition" / "source" / "generated-index.ts").read_text(encoding="utf-8")


def test_composer_requires_every_contract_to_have_an_accepted_bundle(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    args = build_args("composer-fail")
    args["options"]["fakeFailures"] = {
        "inbox-toolbar/candidate-1": "action-pressure",
    }

    result = ui_build_recursive(args, fake_context(tmp_path))

    assert result["status"] == "error"
    assert result["data"]["failedNodeId"] == "inbox-toolbar"
