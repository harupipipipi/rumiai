from __future__ import annotations

import json
from pathlib import Path

from tests.ui_compiler_test_utils import build_args, fake_context, write_pass_package

from domain.tool.ui_compiler_tools import ui_build_recursive
from domain.tool.ui_compiler_runtime.foundation_generator import _validate_foundation_output


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
        assert (root / "primitives" / "Button.tsx").is_file()
        assert (root / "specimen" / "type-specimen.html").is_file()
        assert (root / "specimen" / "density-specimen.html").is_file()
        assert (root / "specimen" / "primitive-gallery.html").is_file()
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


def test_foundation_validation_rejects_non_token_colors_outside_tokens(tmp_path: Path) -> None:
    root = tmp_path / "foundation"
    (root / "primitives").mkdir(parents=True)
    (root / "specimen").mkdir()
    (root / "foundation.json").write_text(json.dumps({"candidateId": "foundation-1"}), encoding="utf-8")
    (root / "tokens.css").write_text(":root { --rui-action-primary: #3366ff; }", encoding="utf-8")
    (root / "primitive-manifest.json").write_text(json.dumps({"primitives": ["Button"]}), encoding="utf-8")
    (root / "primitives" / "Button.tsx").write_text("export const Button = () => <button style={{ color: '#123456' }} />;", encoding="utf-8")
    (root / "specimen" / "type-specimen.html").write_text("<main>Type</main>", encoding="utf-8")
    (root / "specimen" / "color-specimen.html").write_text("<main>Color</main>", encoding="utf-8")
    (root / "specimen" / "density-specimen.html").write_text("<main>Density</main>", encoding="utf-8")
    (root / "specimen" / "primitive-gallery.html").write_text("<main>Gallery</main>", encoding="utf-8")

    report = _validate_foundation_output(root, {"status": "pass", "score": 0.1})

    assert report["status"] == "fail"
    assert any(issue["code"] == "FOUNDATION_NON_TOKEN_COLOR" for issue in report["issues"])
