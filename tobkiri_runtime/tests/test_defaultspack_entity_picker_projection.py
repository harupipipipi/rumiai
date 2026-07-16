from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import ResolvedTemplate, parse_template, project_resolved_templates  # noqa: E402
from domain.templates.projectors import empty_template_catalog  # noqa: E402


def _template(template_id: str, pieces: list[dict[str, Any]]) -> ResolvedTemplate:
    parsed = parse_template(
        {
            "schema_version": 1,
            "id": template_id,
            "kind": "frontend",
            "version": "1.0.0",
            "status": "active",
            "pieces": pieces,
        },
        trust_level="builtin",
    )
    assert parsed.template is not None, parsed.diagnostics
    return ResolvedTemplate(parsed.template, parsed.diagnostics)


def test_entity_picker_projects_picker_and_generic_slash_command() -> None:
    catalog = project_resolved_templates(
        [
            _template(
                "test.entity_picker",
                [
                    {
                        "id": "profiles_source",
                        "kind": "function",
                        "role": "data_source",
                        "data_source": "agent_profiles",
                        "snapshot": {"items": [{"id": "reviewer", "label": "Reviewer"}]},
                    },
                    {
                        "id": "select_profile",
                        "kind": "function",
                        "role": "action",
                        "action_id": "profiles.select",
                        "execution": {"type": "rumi_function", "qualified_name": "test:select"},
                    },
                    {
                        "id": "profile_picker_piece",
                        "kind": "entity_picker",
                        "picker": {
                            "picker_id": "agent_profile",
                            "label": "Agent profile",
                            "data_source": "agent_profiles",
                            "selection_mode": "multi",
                            "value_scope": "workspace",
                            "on_select_action_id": "profiles.select",
                            "trigger_command": "/agent-profile",
                        },
                    },
                ],
            )
        ]
    )

    picker = catalog["entity_pickers"][0]
    command = next(item for item in catalog["commands"] if item["id"] == "agent-profile")
    assert picker["api_version"] == "rumi.entity_picker.v1"
    assert picker["picker_id"] == "agent_profile"
    assert picker["template_id"] == "test.entity_picker"
    assert picker["projected_id"] == "test.entity_picker:profile_picker_piece"
    assert command["execution"] == {"type": "frontend", "action": "open_entity_picker"}
    assert command["picker_id"] == "agent_profile"
    assert command["args"] == [
        {"name": "query", "type": "string", "required": False, "greedy": True}
    ]

def test_entity_picker_public_id_collision_excludes_both_declarations() -> None:
    catalog = project_resolved_templates(
        [
            _template(
                "test.picker.one",
                [{"id": "first", "kind": "entity_picker", "picker": {"picker_id": "same", "data_source": "one"}}],
            ),
            _template(
                "test.picker.two",
                [{"id": "second", "kind": "entity_picker", "picker": {"picker_id": "same", "data_source": "two"}}],
            ),
        ]
    )

    assert catalog["entity_pickers"] == []
    diagnostic = next(
        item
        for item in catalog["template_diagnostics"]
        if item["code"] == "template.catalog.public_id_collision"
    )
    assert diagnostic["details"]["bucket"] == "entity_pickers"
    assert set(diagnostic["details"]["projected_ids"]) == {
        "test.picker.one:first",
        "test.picker.two:second",
    }


def test_empty_catalog_and_frontend_registry_expose_entity_pickers() -> None:
    assert empty_template_catalog()["entity_pickers"] == []

    registry_path = DEFAULTSPACK_ROOT / "domain" / "frontend" / "registry.py"
    tree = ast.parse(registry_path.read_text(encoding="utf-8"))
    build_catalog = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build_catalog"
    )
    exposed_keys = {
        key.value
        for node in ast.walk(build_catalog)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    assert "entity_pickers" in exposed_keys
