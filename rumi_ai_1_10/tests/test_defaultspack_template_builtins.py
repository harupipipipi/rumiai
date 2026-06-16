from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import build_template_registry, discover_templates, resolve_template  # noqa: E402


BUILTIN_TEMPLATE_IDS = {
    "rumi.model_selector.default",
    "rumi.api_keys.default",
    "rumi.backend.model_routing.default",
}


def test_builtin_templates_are_discovered_from_defaultspack_templates_root():
    result = discover_templates(defaultspack_root=DEFAULTSPACK_ROOT)
    discovered_ids = {template.id for template in result.templates}

    assert BUILTIN_TEMPLATE_IDS.issubset(discovered_ids)
    assert {
        template.id: str(template.trust_level.value if hasattr(template.trust_level, "value") else template.trust_level)
        for template in result.templates
        if template.id in BUILTIN_TEMPLATE_IDS
    } == {template_id: "builtin" for template_id in BUILTIN_TEMPLATE_IDS}
    assert not any(diagnostic.is_error for diagnostic in result.diagnostics)


def test_builtin_templates_resolve_and_include_projector_contract_pieces():
    registry, diagnostics = build_template_registry(defaultspack_root=str(DEFAULTSPACK_ROOT))

    assert not any(diagnostic.is_error for diagnostic in diagnostics)
    for template_id in BUILTIN_TEMPLATE_IDS:
        resolved = resolve_template(template_id, registry)
        assert resolved.ok
        assert resolved.template is not None

        pieces = {piece.id: piece for piece in resolved.template.pieces}
        for piece_id in (
            "model_select",
            "provider_select",
            "api_key_setup",
        ):
            assert piece_id in pieces
            assert pieces[piece_id].kind == "settings_field"

        piece_kinds = {str(piece.kind.value if hasattr(piece.kind, "value") else piece.kind) for piece in pieces.values()}
        assert "backend_service" in piece_kinds
        assert "api_route" in piece_kinds
        assert "settings_section" in piece_kinds
        assert "field_renderer" in piece_kinds
        assert "permission" in piece_kinds
        assert "test_contract" in piece_kinds
        assert any(piece.data.get("role") == "action" for piece in pieces.values())
        assert any(piece.data.get("role") == "data_source" for piece in pieces.values())
