from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import parse_template  # noqa: E402
from domain.templates.projectors import build_template_catalog  # noqa: E402


def test_frontend_component_projects_typed_registry_binding(tmp_path: Path):
    template_path = tmp_path / "templates" / "fixture" / "template.json"
    template_path.parent.mkdir(parents=True)
    template_path.write_text(
        """
        {
          "id": "fixture.component.template",
          "kind": "frontend",
          "version": "1.0.0",
          "status": "active",
          "pieces": [{
            "id": "fixture_status",
            "kind": "frontend_component",
            "part_id": "fixture_field",
            "component_id": "rumi.ui.text",
            "api_version": "rumi.frontend.component.v1",
            "slot": "settings_field",
            "props": {"text": "Pack-owned declaration"},
            "data_source_ids": ["fixture.status"],
            "fallback_component_id": "rumi.ui.unsupported"
          }]
        }
        """,
        encoding="utf-8",
    )

    catalog = build_template_catalog(defaultspack_root=tmp_path)

    binding = catalog["component_bindings"][0]
    assert binding["component"] == "rumi.ui.text"
    assert binding["component_id"] == "rumi.ui.text"
    assert binding["api_version"] == "rumi.frontend.component.v1"
    assert binding["slot"] == "settings_field"
    assert binding["props"] == {"text": "Pack-owned declaration"}
    assert binding["data_source_ids"] == ["fixture.status"]
    assert binding["template_id"] == "fixture.component.template"
    assert binding["trust_level"] == "builtin"


def test_frontend_component_default_api_version_is_stable():
    parsed = parse_template(
        {
            "id": "fixture.component.default",
            "kind": "frontend",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {
                    "id": "fixture_badge",
                    "kind": "frontend_component",
                    "part_id": "fixture_field",
                    "component": "rumi.ui.badge",
                }
            ],
        }
    )
    assert parsed.template is not None

    from domain.templates.models import ResolvedTemplate
    from domain.templates.projectors import project_resolved_templates

    catalog = project_resolved_templates([ResolvedTemplate(template=parsed.template)])
    binding = catalog["component_bindings"][0]
    assert binding["component_id"] == "rumi.ui.badge"
    assert binding["api_version"] == "rumi.frontend.component.v1"
