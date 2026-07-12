from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates import parse_template  # noqa: E402
from domain.templates.activation import TemplateActivationPlanner  # noqa: E402
from domain.templates.projectors import build_template_catalog  # noqa: E402
from domain.templates.registry import TemplateRegistry  # noqa: E402


def _template(
    template_id: str,
    *,
    version: str = "1.0.0",
    status: str = "active",
    provides: list[str] | None = None,
    requires: list[str] | None = None,
    dependencies: list[Any] | None = None,
    extends: str | list[str] | None = None,
    pieces: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema_version": 1,
        "id": template_id,
        "kind": "backend",
        "version": version,
        "status": status,
        "capabilities": {
            "provides": provides or [],
            "requires": requires or [],
            "permissions": [],
        },
        "pieces": pieces or [],
    }
    if dependencies is not None:
        raw["dependencies"] = dependencies
    if extends is not None:
        raw["extends"] = extends
    return raw


def _registry(*templates: dict[str, Any]) -> TemplateRegistry:
    registry = TemplateRegistry()
    for raw in templates:
        parsed = parse_template(raw)
        assert parsed.template is not None, parsed.diagnostics
        registry.register(parsed.template, validate=False)
    return registry


def _write_template(root: Path, raw: dict[str, Any]) -> None:
    template_dir = root / "templates" / raw["id"].replace(".", "_")
    template_dir.mkdir(parents=True)
    (template_dir / "template.json").write_text(json.dumps(raw), encoding="utf-8")


def test_activation_required_dependency_capability_satisfies_requires_transitively():
    registry = _registry(
        _template("base", provides=["cap.base"]),
        _template("middle", dependencies=["base"], provides=["cap.middle"]),
        _template("consumer", dependencies=["middle"], requires=["cap.base", "cap.middle"]),
    )

    plan = TemplateActivationPlanner(registry).build()

    assert plan.ordered_template_ids == ["base", "middle", "consumer"]
    assert plan.states["consumer"].projectable is True
    assert plan.states["consumer"].capability_providers["cap.base"] == ["base"]
    assert plan.states["consumer"].capability_providers["cap.middle"] == ["middle"]


def test_activation_missing_required_dependency_blocks_runtime_projection(tmp_path):
    _write_template(
        tmp_path,
        _template(
            "consumer",
            dependencies=["missing"],
            pieces=[
                {
                    "id": "action",
                    "kind": "function",
                    "role": "action",
                    "action_id": "blocked_action",
                }
            ],
        ),
    )

    catalog = build_template_catalog(defaultspack_root=tmp_path)

    assert catalog["templates"][0]["projectable"] is False
    assert catalog["templates"][0]["blocked_by"] == ["missing"]
    assert catalog["actions"] == []
    assert any(
        item["code"] == "template.dependency.missing" and item["template_id"] == "consumer"
        for item in catalog["template_diagnostics"]
    )


def test_activation_optional_dependency_warns_without_blocking():
    registry = _registry(
        _template(
            "consumer",
            dependencies=[{"id": "missing", "optional": True}],
        )
    )

    plan = TemplateActivationPlanner(registry).build()

    assert plan.states["consumer"].projectable is True
    assert plan.states["consumer"].blocked_by == []
    assert [diagnostic.code for diagnostic in plan.states["consumer"].diagnostics] == [
        "template.dependency.missing"
    ]
    assert plan.states["consumer"].diagnostics[0].severity == "warning"


def test_activation_inactive_dependency_and_version_mismatch_block():
    registry = _registry(
        _template("disabled_dep", status="disabled"),
        _template("versioned_dep", version="1.0.0"),
        _template(
            "consumer",
            dependencies=[
                "disabled_dep",
                {"id": "versioned_dep", "version": ">=2"},
            ],
        ),
    )

    plan = TemplateActivationPlanner(registry).build()
    codes = {diagnostic.code for diagnostic in plan.states["consumer"].diagnostics}

    assert plan.states["consumer"].projectable is False
    assert "disabled_dep" in plan.states["consumer"].blocked_by
    assert "versioned_dep" in plan.states["consumer"].blocked_by
    assert "template.dependency.inactive" in codes
    assert "template.dependency.version_mismatch" in codes


def test_activation_dependency_cycle_blocks_cycle_members():
    registry = _registry(
        _template("a", dependencies=["b"]),
        _template("b", dependencies=["a"]),
        _template("c"),
    )

    plan = TemplateActivationPlanner(registry).build()

    assert plan.ordered_template_ids[-2:] == ["a", "b"]
    assert plan.states["a"].projectable is False
    assert plan.states["b"].projectable is False
    assert plan.states["c"].projectable is True
    assert any(
        diagnostic.code == "template.activation.cycle"
        for diagnostic in plan.states["a"].diagnostics
    )


def test_activation_future_schema_version_blocks_projection(tmp_path):
    _write_template(
        tmp_path,
        {
            **_template(
                "future",
                pieces=[
                    {
                        "id": "action",
                        "kind": "function",
                        "role": "action",
                        "action_id": "future_action",
                    }
                ],
            ),
            "schema_version": 99,
        },
    )

    catalog = build_template_catalog(defaultspack_root=tmp_path)

    assert catalog["templates"][0]["schema_version"] == 99
    assert catalog["templates"][0]["projectable"] is False
    assert catalog["actions"] == []
    assert any(
        item["code"] == "template.schema_version.unsupported"
        for item in catalog["template_diagnostics"]
    )
