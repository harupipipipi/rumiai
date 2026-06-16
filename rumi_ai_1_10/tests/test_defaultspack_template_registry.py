from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import (  # noqa: E402
    TemplateRegistry,
    TemplateRoot,
    TemplateTrustLevel,
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
    assert any(diagnostic.code == "template.registry.duplicate_template" for diagnostic in duplicate_diagnostics)


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
    assert any(diagnostic.code == "template.discovery.json_parse_error" for diagnostic in result.diagnostics)
    assert load_template_file(bad).templates == []


def test_default_roots_are_stable_and_missing_roots_are_ok(tmp_path):
    roots = default_template_roots(tmp_path)

    assert roots == [
        TemplateRoot(tmp_path / "templates", TemplateTrustLevel.BUILTIN),
        TemplateRoot(tmp_path / "user_data" / "shared" / "templates", TemplateTrustLevel.USER),
    ]
    assert discover_templates(defaultspack_root=tmp_path).templates == []
