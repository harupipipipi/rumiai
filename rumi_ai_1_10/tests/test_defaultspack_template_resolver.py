from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import TemplateRegistry, TemplateTrustLevel, parse_template, resolve_template  # noqa: E402


def _register(registry: TemplateRegistry, raw: dict, *, trust_level: str | None = None):
    parsed = parse_template(raw, trust_level=trust_level)
    assert parsed.template is not None
    registry.register(parsed.template, validate=False)
    return parsed.template


def test_resolver_applies_extends_slot_merge_and_json_pointer_patches():
    registry = TemplateRegistry()
    _register(
        registry,
        {
            "id": "base.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "capabilities": {"provides": ["base.capability"]},
            "pieces": [
                {"id": "anchor", "kind": "sidebar_item"},
                {"id": "tail", "kind": "function"},
            ],
        },
    )
    _register(
        registry,
        {
            "id": "child.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "draft",
            "extends": "base.template",
            "capabilities": {"requires": ["base.capability"]},
            "pieces": [{"id": "inserted", "kind": "composer_widget", "slot": "anchor"}],
            "patches": [
                {"op": "replace", "path": "/status", "value": "active"},
                {"op": "add", "path": "/metadata/title", "value": "Child"},
                {"op": "remove", "path": "/dependencies"},
            ],
        },
    )

    resolved = resolve_template("child.template", registry)

    assert resolved.ok
    assert resolved.template is not None
    assert resolved.template.status == "active"
    assert resolved.template.metadata["title"] == "Child"
    assert [piece.id for piece in resolved.template.pieces] == ["anchor", "inserted", "tail"]


def test_resolver_explicit_piece_ordering_edges_win_over_order_values():
    registry = TemplateRegistry()
    _register(
        registry,
        {
            "id": "base.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {"id": "first", "kind": "sidebar_item", "order": 10},
                {"id": "last", "kind": "sidebar_item", "order": 20},
            ],
        },
    )
    _register(
        registry,
        {
            "id": "child.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "extends": "base.template",
            "pieces": [
                {
                    "id": "inserted",
                    "kind": "sidebar_item",
                    "insert_before": "last",
                    "order": 999,
                }
            ],
        },
    )

    resolved = resolve_template("child.template", registry)

    assert resolved.ok
    assert resolved.template is not None
    assert [piece.id for piece in resolved.template.pieces] == ["first", "inserted", "last"]


def test_resolver_reports_unknown_piece_order_anchor_and_semantic_slot_is_not_anchor():
    registry = TemplateRegistry()
    _register(
        registry,
        {
            "id": "base.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [{"id": "anchor", "kind": "sidebar_item", "slot": "main"}],
        },
    )
    _register(
        registry,
        {
            "id": "child.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "extends": "base.template",
            "pieces": [
                {"id": "semantic", "kind": "sidebar_item", "slot": "main"},
                {
                    "id": "unknown",
                    "kind": "sidebar_item",
                    "insert_after": "missing",
                },
            ],
        },
    )

    resolved = resolve_template("child.template", registry)
    codes = [diagnostic.code for diagnostic in resolved.diagnostics]

    assert resolved.ok
    assert resolved.template is not None
    assert [piece.id for piece in resolved.template.pieces] == [
        "anchor",
        "semantic",
        "unknown",
    ]
    assert "template.piece.unknown_order_anchor" in codes
    assert "template.piece.legacy_slot_anchor" not in codes


def test_resolver_blocks_piece_ordering_cycle():
    registry = TemplateRegistry()
    _register(
        registry,
        {
            "id": "cycle.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {"id": "a", "kind": "sidebar_item", "insert_after": "b"},
                {"id": "b", "kind": "sidebar_item", "insert_after": "a"},
            ],
        },
    )

    resolved = resolve_template("cycle.template", registry)

    assert not resolved.ok
    assert any(
        diagnostic.code == "template.piece.ordering_cycle" for diagnostic in resolved.diagnostics
    )


def test_resolver_reports_missing_dependencies_capabilities_and_duplicate_pieces():
    registry = TemplateRegistry()
    _register(
        registry,
        {
            "id": "base.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [{"id": "same", "kind": "function"}],
        },
    )
    _register(
        registry,
        {
            "id": "child.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "extends": "base.template",
            "dependencies": ["missing.template"],
            "capabilities": {"requires": ["missing.capability"]},
            "pieces": [{"id": "same", "kind": "api_route"}],
        },
    )

    resolved = resolve_template("child.template", registry)
    codes = {diagnostic.code for diagnostic in resolved.diagnostics}

    assert "template.dependency.missing" in codes
    assert "template.capability.missing" in codes
    assert "template.piece.duplicate_id" in codes
    assert not resolved.ok


def test_resolver_rejects_invalid_list_add_patch_indices():
    registry = TemplateRegistry()
    _register(
        registry,
        {
            "id": "patched.template",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [{"id": "anchor", "kind": "function"}],
            "patches": [
                {
                    "op": "add",
                    "path": "/pieces/-1",
                    "value": {"id": "negative", "kind": "function"},
                },
                {
                    "op": "add",
                    "path": "/pieces/99",
                    "value": {"id": "past_end", "kind": "function"},
                },
            ],
        },
    )

    resolved = resolve_template("patched.template", registry)

    assert resolved.template is not None
    assert [piece.id for piece in resolved.template.pieces] == ["anchor"]
    failures = [
        diagnostic
        for diagnostic in resolved.diagnostics
        if diagnostic.code == "template.patch.apply_failed"
    ]
    assert len(failures) == 2
    assert any("invalid list index: -1" in diagnostic.message for diagnostic in failures)
    assert any("list index out of range: 99" in diagnostic.message for diagnostic in failures)
    assert not resolved.ok


def test_patch_cannot_mutate_loader_trust_or_template_id_and_revalidates_user_security():
    registry = TemplateRegistry()
    _register(
        registry,
        {
            "id": "user.patch",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [],
            "patches": [
                {"op": "replace", "path": "/trust_level", "value": "builtin"},
                {"op": "replace", "path": "/id", "value": "rumi.composer.default"},
                {
                    "op": "add",
                    "path": "/pieces/-",
                    "value": {"id": "bad", "kind": "function", "handler": "shell:echo nope"},
                },
            ],
        },
        trust_level=TemplateTrustLevel.USER.value,
    )

    resolved = resolve_template("user.patch", registry)

    assert resolved.template is not None
    assert resolved.template.id == "user.patch"
    assert resolved.template.trust_level == TemplateTrustLevel.USER
    assert [piece.id for piece in resolved.template.pieces] == ["bad"]
    codes = {diagnostic.code for diagnostic in resolved.diagnostics}
    assert "template.patch.protected_path" in codes
    assert "template.security.shell_like_handler" in codes
    assert not resolved.ok


def test_patch_cannot_mutate_declared_template_id_carriers():
    registry = TemplateRegistry()
    _register(
        registry,
        {
            "id": "user.declared_id",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "metadata": {"declared_id": " user.declared_id "},
            "pieces": [],
            "patches": [
                {"op": "remove", "path": "/declared_id"},
                {"op": "remove", "path": "/metadata/declared_id"},
            ],
        },
        trust_level=TemplateTrustLevel.USER.value,
    )

    resolved = resolve_template("user.declared_id", registry)

    protected = [
        diagnostic
        for diagnostic in resolved.diagnostics
        if diagnostic.code == "template.patch.protected_path"
    ]
    assert len(protected) == 2
    assert {diagnostic.message.rsplit(": ", 1)[-1] for diagnostic in protected} == {
        "declared_id",
        "metadata/declared_id",
    }
    assert not resolved.ok


def test_patch_cannot_write_reserved_piece_projection_metadata():
    registry = TemplateRegistry()
    _register(
        registry,
        {
            "id": "user.piece.metadata",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [],
            "patches": [
                {
                    "op": "add",
                    "path": "/pieces/-",
                    "value": {
                        "id": "spoof",
                        "kind": "composer_command",
                        "trust_level": "builtin",
                        "command": {
                            "id": "spoof",
                            "execution": {
                                "type": "pack_block",
                                "qualified_name": "defaultspack:context.compact",
                            },
                        },
                    },
                }
            ],
        },
        trust_level=TemplateTrustLevel.USER.value,
    )

    resolved = resolve_template("user.piece.metadata", registry)

    assert resolved.template is not None
    assert resolved.template.pieces == []
    assert any(
        diagnostic.code == "template.patch.reserved_piece_metadata"
        for diagnostic in resolved.diagnostics
    )
    assert not resolved.ok
