from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import ResolvedTemplate, parse_template, project_resolved_templates  # noqa: E402


def _template(
    template_id: str,
    piece: dict[str, Any],
    *,
    trust_level: str = "builtin",
) -> ResolvedTemplate:
    parsed = parse_template(
        {
            "schema_version": 1,
            "id": template_id,
            "kind": "pack",
            "version": "1.0.0",
            "status": "active",
            "pieces": [piece],
        },
        trust_level=trust_level,
    )
    assert parsed.template is not None, parsed.diagnostics
    return ResolvedTemplate(parsed.template, parsed.diagnostics)


@pytest.mark.parametrize(
    ("bucket", "piece_factory"),
    [
        (
            "actions",
            lambda piece_id, public_id: {
                "id": piece_id,
                "kind": "function",
                "role": "action",
                "action_id": public_id,
            },
        ),
        (
            "data_sources",
            lambda piece_id, public_id: {
                "id": piece_id,
                "kind": "function",
                "role": "data_source",
                "data_source": public_id,
            },
        ),
        (
            "commands",
            lambda piece_id, public_id: {
                "id": piece_id,
                "kind": "composer_command",
                "command": {"id": public_id, "execution": {"type": "frontend"}},
            },
        ),
        (
            "tool_policies",
            lambda piece_id, public_id: {
                "id": piece_id,
                "kind": "tool_policy",
                "policy": {"id": public_id, "tool_choice": "auto"},
            },
        ),
        (
            "ai_inputs",
            lambda piece_id, public_id: {
                "id": piece_id,
                "kind": "ai_input",
                "input": {"id": public_id, "params": {}},
            },
        ),
        (
            "api_routes",
            lambda piece_id, public_id: {
                "id": piece_id,
                "kind": "api_route",
                "method": "POST",
                "path": public_id,
            },
        ),
        (
            "backend_services",
            lambda piece_id, public_id: {
                "id": piece_id,
                "kind": "backend_service",
                "service_id": public_id,
            },
        ),
        (
            "permissions",
            lambda piece_id, public_id: {
                "id": piece_id,
                "kind": "permission",
                "permission_id": public_id,
            },
        ),
        (
            "external_io_templates",
            lambda piece_id, public_id: {
                "id": piece_id,
                "kind": "external_io_template",
                "template": {"id": public_id, "direction": "input", "provider": "test"},
            },
        ),
    ],
)
def test_public_id_collision_excludes_all_items(bucket, piece_factory):
    public_id = "/same" if bucket == "api_routes" else "same"
    catalog = project_resolved_templates(
        [
            _template("template.one", piece_factory("first", public_id)),
            _template("template.two", piece_factory("second", public_id)),
        ]
    )

    assert catalog[bucket] == []
    diagnostic = next(
        item
        for item in catalog["template_diagnostics"]
        if item["code"] == "template.catalog.public_id_collision"
    )
    assert diagnostic["details"]["bucket"] == bucket
    assert set(diagnostic["details"]["projected_ids"]) == {
        "template.one:first",
        "template.two:second",
    }


def test_public_id_collision_valid_explicit_replace_keeps_replacer():
    catalog = project_resolved_templates(
        [
            _template(
                "template.base",
                {
                    "id": "base",
                    "kind": "function",
                    "role": "action",
                    "action_id": "same_action",
                },
            ),
            _template(
                "template.replacer",
                {
                    "id": "replacement",
                    "kind": "function",
                    "role": "action",
                    "action_id": "same_action",
                    "override": {
                        "mode": "replace",
                        "target_projected_id": "template.base:base",
                    },
                },
            ),
        ]
    )

    assert [item["projected_id"] for item in catalog["actions"]] == [
        "template.replacer:replacement"
    ]
    assert not any(
        item["code"] == "template.catalog.public_id_collision"
        for item in catalog["template_diagnostics"]
    )


def test_public_id_collision_lower_trust_override_is_rejected():
    catalog = project_resolved_templates(
        [
            _template(
                "template.base",
                {
                    "id": "base",
                    "kind": "function",
                    "role": "action",
                    "action_id": "same_action",
                },
                trust_level="builtin",
            ),
            _template(
                "template.user",
                {
                    "id": "replacement",
                    "kind": "function",
                    "role": "action",
                    "action_id": "same_action",
                    "override": {
                        "mode": "replace",
                        "target_projected_id": "template.base:base",
                    },
                },
                trust_level="user",
            ),
        ]
    )

    assert [item["projected_id"] for item in catalog["actions"]] == ["template.base:base"]
    codes = [item["code"] for item in catalog["template_diagnostics"]]
    assert "template.catalog.invalid_override" in codes
    assert "template.catalog.public_id_collision" not in codes


def test_diagnostic_dedupe_keeps_same_code_with_different_details():
    catalog = project_resolved_templates(
        [
            _template(
                "template.one",
                {
                    "id": "first_action",
                    "kind": "function",
                    "role": "action",
                    "action_id": "same_action",
                },
            ),
            _template(
                "template.two",
                {
                    "id": "second_action",
                    "kind": "function",
                    "role": "action",
                    "action_id": "same_action",
                },
            ),
            _template(
                "template.three",
                {
                    "id": "first_policy",
                    "kind": "tool_policy",
                    "policy": {"id": "same_policy", "tool_choice": "auto"},
                },
            ),
            _template(
                "template.four",
                {
                    "id": "second_policy",
                    "kind": "tool_policy",
                    "policy": {"id": "same_policy", "tool_choice": "auto"},
                },
            ),
        ]
    )

    collisions = [
        item
        for item in catalog["template_diagnostics"]
        if item["code"] == "template.catalog.public_id_collision"
    ]
    assert [item["details"]["bucket"] for item in collisions] == ["actions", "tool_policies"]
