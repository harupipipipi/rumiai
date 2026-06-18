from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import (  # noqa: E402
    RumiTemplate,
    TemplateRegistry,
    TemplateRoot,
    TemplateTrustLevel,
    build_template_registry,
    default_template_roots,
    discover_templates,
    load_template_file,
    parse_template,
)


def _template(template_id: str, *, status: str = "active"):
    parsed = parse_template(
        {
            "id": template_id,
            "kind": "pack",
            "version": "1.0.0",
            "status": status,
            "pieces": [{"id": "fn", "kind": "function"}],
        }
    )
    assert parsed.template is not None
    return parsed.template


def test_registry_register_list_and_get():
    registry = TemplateRegistry()

    registry.register(_template("template.one"))
    registry.register(_template("template.two", status="draft"))

    assert registry.get("template.one") is not None
    assert [template.id for template in registry.list(status="active")] == ["template.one"]

    duplicate_diagnostics = registry.register(_template("template.one"))
    duplicate = next(
        diagnostic
        for diagnostic in duplicate_diagnostics
        if diagnostic.code == "template.registry.duplicate_template"
    )
    assert duplicate.severity == "error"


def test_discovery_reads_template_json_and_keeps_json_parse_errors_as_diagnostics(tmp_path):
    good = tmp_path / "good" / "template.json"
    good.parent.mkdir()
    good.write_text(
        json.dumps(
            {
                "id": "discovered.template",
                "kind": "pack",
                "version": "1.0.0",
                "status": "active",
                "pieces": [{"id": "fn", "kind": "function"}],
            }
        ),
        encoding="utf-8",
    )
    bad = tmp_path / "bad" / "template.json"
    bad.parent.mkdir()
    bad.write_text("{ broken", encoding="utf-8")

    result = discover_templates([tmp_path])

    assert [template.id for template in result.templates] == ["discovered.template"]
    assert any(
        diagnostic.code == "template.discovery.json_parse_error"
        for diagnostic in result.diagnostics
    )
    assert load_template_file(bad).templates == []


def test_default_roots_are_stable_and_missing_roots_are_ok(tmp_path):
    roots = default_template_roots(tmp_path)

    assert roots == [
        TemplateRoot(tmp_path / "templates", TemplateTrustLevel.BUILTIN),
        TemplateRoot(tmp_path / "user_data" / "shared" / "templates", TemplateTrustLevel.USER),
    ]
    assert discover_templates(defaultspack_root=tmp_path).templates == []


def test_user_template_cannot_override_builtin_with_same_id(tmp_path):
    builtin = tmp_path / "templates" / "shared" / "template.json"
    user = tmp_path / "user_data" / "shared" / "templates" / "shared" / "template.json"
    builtin.parent.mkdir(parents=True)
    user.parent.mkdir(parents=True)
    template = {
        "id": "shared.template",
        "kind": "pack",
        "version": "1.0.0",
        "status": "active",
        "pieces": [{"id": "fn", "kind": "function"}],
    }
    builtin.write_text(
        json.dumps({**template, "metadata": {"source": "builtin"}}), encoding="utf-8"
    )
    user.write_text(json.dumps({**template, "metadata": {"source": "user"}}), encoding="utf-8")

    registry, diagnostics = build_template_registry(defaultspack_root=str(tmp_path))

    registered = registry.get("shared.template")
    assert registered is not None
    assert registered.trust_level == TemplateTrustLevel.BUILTIN
    assert registered.metadata["source"] == "builtin"
    duplicate = next(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.code == "template.registry.duplicate_template"
    )
    assert duplicate.severity == "error"
    assert duplicate.source_path == str(user)


def test_user_template_cannot_override_builtin_with_whitespace_variant_id(tmp_path):
    builtin = tmp_path / "templates" / "shared" / "template.json"
    user = tmp_path / "user_data" / "shared" / "templates" / "shared" / "template.json"
    builtin.parent.mkdir(parents=True)
    user.parent.mkdir(parents=True)
    template = {
        "id": "shared.template",
        "kind": "pack",
        "version": "1.0.0",
        "status": "active",
        "pieces": [{"id": "fn", "kind": "function"}],
    }
    builtin.write_text(
        json.dumps({**template, "metadata": {"source": "builtin"}}), encoding="utf-8"
    )
    user.write_text(
        json.dumps({**template, "id": " shared.template ", "metadata": {"source": "user"}}),
        encoding="utf-8",
    )

    registry, diagnostics = build_template_registry(defaultspack_root=str(tmp_path))

    registered = registry.get("shared.template")
    assert registered is not None
    assert registered.trust_level == TemplateTrustLevel.BUILTIN
    assert registered.metadata["source"] == "builtin"
    assert registry.get(" shared.template ") is None
    assert any(diagnostic.code == "template.invalid_id" for diagnostic in diagnostics)
    duplicate = next(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.code == "template.registry.duplicate_template"
    )
    assert duplicate.severity == "error"
    assert duplicate.source_path == str(user)


def test_registry_rejects_direct_noncanonical_template_id():
    registry = TemplateRegistry()
    diagnostics = registry.register(
        RumiTemplate(
            id=" direct.template ",
            kind="pack",
            version="1.0.0",
            status="active",
        )
    )

    assert registry.get("direct.template") is None
    assert any(
        diagnostic.code == "template.registry.noncanonical_template_id"
        for diagnostic in diagnostics
    )
