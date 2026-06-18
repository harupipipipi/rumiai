from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates.contracts import run_template_contracts  # noqa: E402
from domain.templates.projectors import build_template_catalog  # noqa: E402


def _catalog(assertions: list[object]) -> dict:
    return {
        "templates": [{"id": "template.active", "projectable": True}],
        "actions": [{"action_id": "do_work", "projected_id": "template.active:do_work"}],
        "data_sources": [{"data_source": "work_status"}],
        "backend_services": [{"service_id": "worker"}],
        "api_routes": [],
        "permissions": [{"permission_id": "work.run"}],
        "settings_sections": [
            {
                "id": "models",
                "fields": [{"id": "preferred_model", "type": "model_select"}],
            }
        ],
        "tool_policies": [{"id": "default_tools", "allowed_tools": ["web_search"]}],
        "template_diagnostics": [{"code": "template.info", "severity": "info"}],
        "test_contracts": [
            {
                "id": "contract",
                "contract_id": "contract.default",
                "assertions": assertions,
            }
        ],
    }


def test_template_contract_assertion_types_pass():
    catalog = _catalog(
        [
            {"type": "catalog_contains", "bucket": "actions", "match": {"action_id": "do_work"}},
            {"type": "catalog_excludes", "bucket": "actions", "match": {"action_id": "missing"}},
            {"type": "route_resolves", "method": "POST", "path": "/api/work"},
            {"type": "route_absent", "method": "GET", "path": "/api/missing"},
            {"type": "function_registered", "function_id": "do_work"},
            {"type": "function_absent", "function_id": "missing"},
            {"type": "permission_declared", "permission_id": "work.run"},
            {
                "type": "setting_field_exists",
                "section_id": "models",
                "field_id": "preferred_model",
                "field_type": "model_select",
            },
            {"type": "tool_policy_resolves", "policy_id": "default_tools"},
            {"type": "diagnostic_absent", "code": "template.error"},
            {"type": "template_projectable", "template_id": "template.active"},
            {"type": "template_not_projectable", "template_id": "template.missing"},
        ]
    )

    result = run_template_contracts(
        catalog,
        routes=[{"method": "POST", "path": "/api/work"}],
        functions={"do_work": object()},
    )

    assert result.passed
    assert not result.failures


def test_template_contract_reports_malformed_unknown_and_legacy_string():
    catalog = _catalog(
        [
            "catalog.actions includes do_work",
            {"type": "not_real"},
            42,
            {"type": "catalog_contains", "bucket": "actions", "match": {"action_id": "missing"}},
        ]
    )

    result = run_template_contracts(catalog, routes=[], functions={})

    assert not result.passed
    assert [warning.assertion_type for warning in result.warnings] == ["legacy_string"]
    assert {failure.assertion_type for failure in result.failures} == {
        "not_real",
        "malformed",
        "catalog_contains",
    }


def test_all_shipped_template_contracts_are_machine_executable_and_pass():
    catalog = build_template_catalog(defaultspack_root=DEFAULTSPACK_ROOT)
    result = run_template_contracts(catalog, defaultspack_root=DEFAULTSPACK_ROOT)

    assert result.passed, result.to_dict()
    assert not result.warnings
    assert result.results
