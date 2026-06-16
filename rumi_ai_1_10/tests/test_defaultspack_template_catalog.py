from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.frontend.registry import FrontendRegistry  # noqa: E402
from domain.templates import ResolvedTemplate, build_template_catalog, parse_template, project_resolved_templates  # noqa: E402


def _field_types(sections: list[dict]) -> set[str]:
    return {
        str(field.get("type"))
        for section in sections
        for field in section.get("fields", [])
        if isinstance(field, dict) and field.get("type")
    }


def test_template_projector_builds_stable_catalog_metadata():
    catalog = build_template_catalog(defaultspack_root=DEFAULTSPACK_ROOT)

    template_ids = {template["id"] for template in catalog["templates"]}
    assert "rumi.model_selector.default" in template_ids
    assert "rumi.api_keys.default" in template_ids
    assert "rumi.backend.model_routing.default" in template_ids

    assert _field_types(catalog["settings_sections"]) >= {"model_select", "provider_select", "api_key_setup"}
    assert any("model_select" in renderer.get("field_types", []) for renderer in catalog["field_renderers"])
    assert any("model_select" in binding.get("field_types", []) for binding in catalog["component_bindings"])
    assert any(item.get("action_id") == "ai_set_preferred_model" for item in catalog["actions"])
    assert any(item.get("data_source") == "provider_key_status" for item in catalog["data_sources"])
    assert any(item.get("service_id") == "model_router" for item in catalog["backend_services"])
    assert catalog["api_routes"] == []
    assert any(
        item.get("route_metadata", {}).get("path") == "/api/ai/models/route"
        for item in catalog["test_contracts"]
    )
    assert any(item.get("permission_id") == "api_key.use" for item in catalog["permissions"])
    assert not catalog["template_diagnostics"]

    projected_ids = {
        item.get("projected_id")
        for key in ("actions", "data_sources", "backend_services", "permissions", "test_contracts")
        for item in catalog[key]
    }
    assert "rumi.backend.model_routing.default:model_router_service" in projected_ids

    model_section = next(section for section in catalog["settings_sections"] if section["id"] == "models")
    model_field = next(field for field in model_section["fields"] if field["id"] == "model_select")
    assert model_field["piece_id"] == "model_select"
    assert model_field["template_id"] == "rumi.model_selector.default"
    assert model_field["projected_id"] == "rumi.model_selector.default:model_select"


def test_frontend_catalog_merges_template_metadata_without_dropping_existing_keys():
    with patch("domain.frontend.registry.AIClient") as mock_client:
        mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
        registry = FrontendRegistry(pack_root=DEFAULTSPACK_ROOT)
        catalog = registry.build_catalog()
        settings = registry.get_settings()

    for key in (
        "app",
        "agent_service",
        "shell",
        "parts",
        "component_bindings",
        "sidebar",
        "settings",
        "chat_rendering",
        "skills",
        "routes",
        "extension_points",
        "diagnostics",
    ):
        assert key in catalog

    assert "templates" in catalog
    assert "field_renderers" in catalog
    assert "data_sources" in catalog
    assert "actions" in catalog
    assert "backend_services" in catalog
    assert "api_routes" in catalog
    assert "permissions" in catalog
    assert "template_diagnostics" in catalog

    assert any(template["id"] == "rumi.model_selector.default" for template in catalog["templates"])
    assert "model_select" in _field_types(catalog["settings"]["sections"])
    assert "api_key_setup" in _field_types(settings["sections"])
    assert any("model_select" in renderer.get("field_types", []) for renderer in catalog["field_renderers"])


def test_projected_settings_fields_namespace_piece_ids_and_diagnose_setting_key_collisions():
    parsed_one = parse_template(
        {
            "id": "template.one",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {
                    "id": "shared",
                    "kind": "settings_field",
                    "section_id": "models",
                    "type": "text",
                }
            ],
        }
    )
    parsed_two = parse_template(
        {
            "id": "template.two",
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [
                {
                    "id": "shared",
                    "kind": "settings_field",
                    "section_id": "models",
                    "type": "text",
                }
            ],
        }
    )
    assert parsed_one.template is not None
    assert parsed_two.template is not None

    catalog = project_resolved_templates(
        [
            ResolvedTemplate(template=parsed_one.template),
            ResolvedTemplate(template=parsed_two.template),
        ]
    )

    models = next(section for section in catalog["settings_sections"] if section["id"] == "models")
    projected_ids = {field["projected_id"] for field in models["fields"]}
    assert projected_ids == {"template.one:shared", "template.two:shared"}
    assert {field["id"] for field in models["fields"]} == {"shared"}
    assert any(
        diagnostic["code"] == "template.catalog.settings_field_id_collision"
        for diagnostic in catalog["template_diagnostics"]
    )


def test_malformed_template_does_not_break_frontend_catalog(tmp_path):
    bad_template = tmp_path / "templates" / "broken" / "template.json"
    bad_template.parent.mkdir(parents=True)
    bad_template.write_text("{ broken", encoding="utf-8")

    with patch("domain.frontend.registry.AIClient") as mock_client:
        mock_client.return_value.list_models.return_value = [{"id": "stub/default"}]
        catalog = FrontendRegistry(pack_root=tmp_path).build_catalog()

    assert "app" in catalog
    assert "settings" in catalog
    assert catalog["templates"] == []
    assert any(item["code"] == "template.discovery.json_parse_error" for item in catalog["diagnostics"])
    assert any(item["code"] == "template.discovery.json_parse_error" for item in catalog["template_diagnostics"])
