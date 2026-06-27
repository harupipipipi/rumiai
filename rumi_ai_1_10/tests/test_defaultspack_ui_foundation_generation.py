from __future__ import annotations

import json
from pathlib import Path

from tests.ui_compiler_test_utils import build_args, fake_context, write_pass_package

from domain.tool.ui_compiler_tools import ui_build_recursive


def test_foundation_candidates_and_accepted_foundation_are_persisted(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    result = ui_build_recursive(build_args("foundation-run"), fake_context(tmp_path))
    run_root = tmp_path / ".rumi" / "ui" / "runs" / "foundation-run"
    candidate_roots = sorted((run_root / "foundation" / "candidates").glob("foundation-*"))
    accepted = json.loads((run_root / "foundation" / "accepted" / "foundation.json").read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    assert len(candidate_roots) == 3
    for root in candidate_roots:
        assert (root / "foundation.json").is_file()
        assert (root / "tokens.css").is_file()
        assert (root / "primitive-manifest.json").is_file()
        assert (root / "specimen" / "type-specimen.html").is_file()
    assert accepted["direction"]["productMode"] == "utility"
    assert "Button" in accepted["primitives"]


def test_foundation_tokens_use_semantic_custom_properties(tmp_path: Path) -> None:
    write_pass_package(tmp_path / "project")
    ui_build_recursive(build_args("foundation-token-run"), fake_context(tmp_path))
    tokens = (tmp_path / ".rumi" / "ui" / "runs" / "foundation-token-run" / "foundation" / "accepted" / "tokens.css").read_text(
        encoding="utf-8"
    )

    assert "--rui-action-primary" in tokens
    assert "--rui-space-4" in tokens
