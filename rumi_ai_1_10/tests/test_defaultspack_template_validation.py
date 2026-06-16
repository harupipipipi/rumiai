from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import TemplatePieceKind, has_errors, parse_template  # noqa: E402


def test_parse_template_accepts_allowed_piece_kinds():
    raw = {
        "id": "sample.template",
        "kind": "pack",
        "version": "1.0.0",
        "status": "active",
        "pieces": [{"id": "fn", "kind": "function", "entrypoint": "handlers.fn"}],
    }

    result = parse_template(raw)

    assert result.ok
    assert result.template is not None
    assert result.template.pieces[0].kind == TemplatePieceKind.FUNCTION


def test_parse_template_reports_required_and_enum_errors():
    result = parse_template(
        {
            "id": "bad.template",
            "kind": "unknown_kind",
            "version": "",
            "status": "active",
            "pieces": [{"id": "piece", "kind": "not_allowed"}],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert has_errors(result.diagnostics)
    assert "template.missing_required" in codes
    assert "template.invalid_kind" in codes
    assert "template.piece.invalid_kind" in codes


def test_duplicate_piece_ids_are_diagnostic_warnings():
    result = parse_template(
        {
            "id": "dup.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {"id": "same", "kind": "function"},
                {"id": "same", "kind": "api_route"},
            ],
        }
    )

    duplicate = [diagnostic for diagnostic in result.diagnostics if diagnostic.code == "template.piece.duplicate_id"]
    assert duplicate
    assert duplicate[0].severity == "warning"
    assert result.ok
