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


def test_reference_validation_reports_missing_renderers_permissions_and_route_metadata():
    result = parse_template(
        {
            "id": "bad.refs",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "capabilities": {"permissions": ["missing.permission"]},
            "pieces": [
                {"id": "field", "kind": "settings_field", "type": "unknown_field_type"},
                {"id": "renderer", "kind": "field_renderer", "field_types": []},
                {"id": "route_contract", "kind": "test_contract", "route_metadata": {"method": "GET"}},
            ],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.reference.settings_field_renderer_missing" in codes
    assert "template.reference.field_renderer_missing_field_types" in codes
    assert "template.reference.permission_missing_piece" in codes
    assert "template.reference.route_metadata_missing_method_path" in codes
    assert not result.ok


def test_reference_validation_reports_duplicate_action_and_data_source_ids():
    result = parse_template(
        {
            "id": "dup.refs",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {"id": "first_action", "kind": "function", "role": "action", "action_id": "same_action"},
                {"id": "second_action", "kind": "function", "role": "action", "action_id": "same_action"},
                {"id": "first_source", "kind": "function", "role": "data_source", "data_source": "same_source"},
                {"id": "second_source", "kind": "function", "role": "data_source", "data_source": "same_source"},
            ],
        }
    )

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "template.reference.duplicate_action_id" in codes
    assert "template.reference.duplicate_data_source_id" in codes
    assert not result.ok


def test_non_builtin_handler_refs_are_metadata_only_by_default():
    result = parse_template(
        {
            "id": "user.handler",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "trust_level": "user",
            "pieces": [
                {
                    "id": "action",
                    "kind": "function",
                    "role": "action",
                    "action_id": "user_action",
                    "handler_ref": "domain.somewhere:run",
                }
            ],
        }
    )

    diagnostic = next(
        item
        for item in result.diagnostics
        if item.code == "template.reference.non_builtin_handler_not_executable"
    )
    assert diagnostic.severity == "warning"
    assert result.ok
