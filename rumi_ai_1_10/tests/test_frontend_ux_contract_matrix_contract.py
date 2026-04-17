from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "rumi_ai_1_10"
QUALITY_PACK_DIR = PACKAGE_ROOT / "docs" / "quality_pack"
MATRIX_PATH = QUALITY_PACK_DIR / "frontend_ux_contract_matrix.yaml"
SCENARIO_FILES = sorted(QUALITY_PACK_DIR.glob("manual_regression_scenarios*.yaml"))
APP_TSX = PACKAGE_ROOT / "frontend" / "src" / "App.tsx"

REQUIRED_PAGES = {"setup", "dashboard", "packs", "pack_detail", "flows", "settings"}
REQUIRED_APP_SHELL_BEHAVIORS = {
    "router.basename_is_panel",
    "setup_redirect_guard",
    "theme_class_switch",
    "dark_mode_class_switch",
    "toast_container_available",
    "dialog_container_available",
}
ROUTE_SIGNATURES = {
    "/setup": ['path="/setup"'],
    "/": ["Route index element={<Dashboard />}"],
    "packs": ['path="packs"'],
    "packs/:id": ['path="packs/:id"'],
    "flows": ['path="flows"'],
    "settings": ['path="settings"'],
}


def _load_matrix() -> dict:
    data = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("version") == 1
    return data


def _collect_scenario_ids() -> set[str]:
    ids: set[str] = set()
    for scenario_file in SCENARIO_FILES:
        data = yaml.safe_load(scenario_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        scenarios = data.get("scenarios")
        assert isinstance(scenarios, list)
        for scenario in scenarios:
            assert isinstance(scenario, dict)
            scenario_id = scenario.get("id")
            assert isinstance(scenario_id, str)
            ids.add(scenario_id)
    return ids


def test_frontend_ux_contract_matrix_exists_and_has_required_roots():
    assert MATRIX_PATH.exists()
    matrix = _load_matrix()
    assert matrix.get("owner") == "quality-pack"
    assert isinstance(matrix.get("description"), str)
    assert isinstance(matrix.get("app_shell_contracts"), dict)
    assert isinstance(matrix.get("pages"), list)
    assert len(matrix["pages"]) >= 6


def test_frontend_ux_contract_matrix_app_shell_contract_shape():
    app_shell = _load_matrix()["app_shell_contracts"]
    assert isinstance(app_shell.get("required_components"), list)
    assert isinstance(app_shell.get("required_behaviors"), list)
    assert isinstance(app_shell.get("manual_scenarios"), list)
    assert isinstance(app_shell.get("automated_tests"), list)
    assert REQUIRED_APP_SHELL_BEHAVIORS.issubset(set(app_shell["required_behaviors"]))
    assert len(app_shell["manual_scenarios"]) >= 6
    assert len(app_shell["automated_tests"]) >= 2


def test_frontend_ux_contract_matrix_page_contracts_have_minimum_density():
    pages = _load_matrix()["pages"]
    seen_pages: set[str] = set()
    for page in pages:
        assert isinstance(page, dict)
        page_name = page.get("page")
        assert isinstance(page_name, str)
        seen_pages.add(page_name)

        assert isinstance(page.get("app_route"), str)
        assert isinstance(page.get("component"), str)
        assert isinstance(page.get("required_states"), list)
        assert isinstance(page.get("dom_contracts"), list)
        assert isinstance(page.get("manual_scenarios"), list)
        assert isinstance(page.get("automated_tests"), list)

        assert len(page["required_states"]) >= 6
        assert len(page["dom_contracts"]) >= 6
        assert len(page["manual_scenarios"]) >= 8
        assert len(page["automated_tests"]) >= 2

    assert REQUIRED_PAGES.issubset(seen_pages)


def test_frontend_ux_contract_matrix_references_existing_components_and_tests():
    matrix = _load_matrix()
    app_shell = matrix["app_shell_contracts"]

    component_paths = list(app_shell["required_components"])
    for page in matrix["pages"]:
        component_paths.append(page["component"])

    for component in component_paths:
        component_path = PACKAGE_ROOT / component
        assert component_path.exists(), f"missing component file: {component}"

    test_refs = list(app_shell["automated_tests"])
    for page in matrix["pages"]:
        test_refs.extend(page["automated_tests"])

    for test_ref in test_refs:
        assert isinstance(test_ref, str)
        test_file = test_ref.split("::", 1)[0]
        test_path = REPO_ROOT / test_file
        assert test_path.exists(), f"missing test file: {test_file}"


def test_frontend_ux_contract_matrix_references_existing_manual_scenarios():
    scenario_ids = _collect_scenario_ids()
    matrix = _load_matrix()
    app_shell = matrix["app_shell_contracts"]

    for scenario_id in app_shell["manual_scenarios"]:
        assert isinstance(scenario_id, str)
        assert scenario_id in scenario_ids, f"unknown scenario id: {scenario_id}"

    for page in matrix["pages"]:
        for scenario_id in page["manual_scenarios"]:
            assert isinstance(scenario_id, str)
            assert scenario_id in scenario_ids, f"unknown scenario id: {scenario_id}"


def test_frontend_ux_contract_matrix_routes_match_app_router_definitions():
    app_text = APP_TSX.read_text(encoding="utf-8")
    for app_route, signatures in ROUTE_SIGNATURES.items():
        assert any(sig in app_text for sig in signatures), f"missing app route: {app_route}"

    page_routes = {page["app_route"] for page in _load_matrix()["pages"]}
    assert set(ROUTE_SIGNATURES).issubset(page_routes)
