from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import TemplateRegistry, parse_template, resolve_template  # noqa: E402


def _register(registry: TemplateRegistry, raw: dict):
    parsed = parse_template(raw)
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
