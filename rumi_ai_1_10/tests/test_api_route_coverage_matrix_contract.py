from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "rumi_ai_1_10"
QUALITY_PACK_DIR = PACKAGE_ROOT / "docs" / "quality_pack"
MATRIX_PATH = QUALITY_PACK_DIR / "api_route_coverage_matrix.yaml"
SCENARIO_FILES = sorted(QUALITY_PACK_DIR.glob("manual_regression_scenarios*.yaml"))

CORE_ECOSYSTEM_FILES = [
    PACKAGE_ROOT / "core_runtime" / "core_pack" / "core_control_panel" / "ecosystem.json",
    PACKAGE_ROOT / "core_runtime" / "core_pack" / "core_setup" / "ecosystem.json",
    PACKAGE_ROOT / "core_runtime" / "core_pack" / "core_viewer_capability" / "ecosystem.json",
    PACKAGE_ROOT / "core_runtime" / "core_pack" / "core_desktop_capability" / "ecosystem.json",
]

REQUIRED_HARDCODED_ROUTES: set[tuple[str, str]] = {
    ("GET", "/health"),
    ("GET", "/api/packs"),
    ("GET", "/api/packs/pending"),
    ("GET", "/api/packs/{pack_id}/status"),
    ("GET", "/api/packs/{pack_id}/dependencies"),
    ("GET", "/api/runtime/available"),
    ("GET", "/api/containers"),
    ("GET", "/api/privileges"),
    ("GET", "/api/docker/status"),
    ("GET", "/api/network/list"),
    ("GET", "/api/secrets"),
    ("GET", "/api/secrets/grants"),
    ("GET", "/api/secrets/grants/{pack_id}"),
    ("GET", "/api/stores"),
    ("GET", "/api/stores/shared"),
    ("GET", "/api/units"),
    ("GET", "/api/capability/blocked"),
    ("GET", "/api/capability/grants"),
    ("GET", "/api/capability/requests"),
    ("GET", "/api/pip/blocked"),
    ("GET", "/api/pip/requests"),
    ("GET", "/api/flows"),
    ("GET", "/api/routes"),
    ("POST", "/api/network/grant"),
    ("POST", "/api/network/revoke"),
    ("POST", "/api/network/check"),
    ("POST", "/api/packs/scan"),
    ("POST", "/api/packs/import"),
    ("POST", "/api/packs/apply"),
    ("POST", "/api/secrets/set"),
    ("POST", "/api/secrets/delete"),
    ("POST", "/api/secrets/grants/{pack_id}"),
    ("POST", "/api/stores/create"),
    ("POST", "/api/units/publish"),
    ("POST", "/api/units/execute"),
    ("POST", "/api/pip/candidates/scan"),
    ("POST", "/api/pip/requests/{candidate_key}/approve"),
    ("POST", "/api/pip/requests/{candidate_key}/reject"),
    ("POST", "/api/pip/blocked/{candidate_key}/unblock"),
    ("POST", "/api/capability/candidates/scan"),
    ("POST", "/api/capability/requests/{candidate_key}/approve"),
    ("POST", "/api/capability/requests/{candidate_key}/reject"),
    ("POST", "/api/capability/blocked/{candidate_key}/unblock"),
    ("POST", "/api/capability/grants/batch"),
    ("POST", "/api/stores/shared/approve"),
    ("POST", "/api/stores/shared/revoke"),
    ("POST", "/api/capability/grants/grant"),
    ("POST", "/api/capability/grants/revoke"),
    ("POST", "/api/packs/{pack_id}/approve"),
    ("POST", "/api/packs/{pack_id}/approve-rule"),
    ("POST", "/api/packs/{pack_id}/reject"),
    ("POST", "/api/containers/{pack_id}/start"),
    ("POST", "/api/containers/{pack_id}/stop"),
    ("POST", "/api/privileges/{pack_id}/grant/{privilege_id}"),
    ("POST", "/api/privileges/{pack_id}/execute/{privilege_id}"),
    ("POST", "/api/routes/reload"),
    ("POST", "/api/flows/{flow_id}/run"),
    ("DELETE", "/api/secrets/grants/{pack_id}"),
    ("DELETE", "/api/secrets/grants/{pack_id}/{secret_key}"),
    ("DELETE", "/api/containers/{pack_id}"),
    ("DELETE", "/api/packs/{pack_id}"),
}


def _load_matrix() -> list[dict]:
    data = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("version") == 1
    routes = data.get("routes")
    assert isinstance(routes, list)
    return routes


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


def _core_ecosystem_routes() -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for eco_file in CORE_ECOSYSTEM_FILES:
        data = yaml.safe_load(eco_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        routes = data.get("api_routes")
        assert isinstance(routes, list)
        for route in routes:
            assert isinstance(route, dict)
            method = str(route.get("method", "")).upper()
            path = route.get("path")
            path_pattern = route.get("path_pattern")
            resolved = path if isinstance(path, str) else path_pattern
            assert isinstance(resolved, str)
            result.add((method, resolved))
    return result


def _matrix_route_signatures(routes: Iterable[dict]) -> set[tuple[str, str]]:
    signatures: set[tuple[str, str]] = set()
    for route in routes:
        method = route.get("method")
        path = route.get("route")
        assert isinstance(method, str)
        assert isinstance(path, str)
        signatures.add((method.upper(), path))
    return signatures


def test_api_route_coverage_matrix_exists():
    assert MATRIX_PATH.exists()


def test_api_route_coverage_matrix_has_minimum_routes_and_unique_signatures():
    routes = _load_matrix()
    assert len(routes) >= 75
    signatures = _matrix_route_signatures(routes)
    assert len(signatures) == len(routes)


def test_api_route_coverage_matrix_entries_have_required_fields():
    required = {"method", "route", "source", "manual_scenarios", "automated_tests"}
    for route in _load_matrix():
        assert isinstance(route, dict)
        missing = required - set(route.keys())
        assert not missing, f"route entry missing fields: {missing}"
        assert isinstance(route["manual_scenarios"], list) and len(route["manual_scenarios"]) >= 2
        assert isinstance(route["automated_tests"], list) and len(route["automated_tests"]) >= 1


def test_api_route_coverage_matrix_manual_scenario_references_exist():
    scenario_ids = _collect_scenario_ids()
    for route in _load_matrix():
        for scenario_id in route["manual_scenarios"]:
            assert isinstance(scenario_id, str)
            assert scenario_id in scenario_ids, f"unknown scenario id: {scenario_id}"


def test_api_route_coverage_matrix_automated_test_files_exist():
    for route in _load_matrix():
        for test_ref in route["automated_tests"]:
            assert isinstance(test_ref, str)
            test_file = test_ref.split("::", 1)[0]
            test_path = REPO_ROOT / test_file
            assert test_path.exists(), f"missing test file: {test_file}"


def test_api_route_coverage_matrix_covers_required_hardcoded_routes():
    matrix_routes = _matrix_route_signatures(_load_matrix())
    assert REQUIRED_HARDCODED_ROUTES.issubset(matrix_routes)


def test_api_route_coverage_matrix_covers_core_ecosystem_api_routes():
    matrix_routes = _matrix_route_signatures(_load_matrix())
    matrix_routes_with_alias = set(matrix_routes)
    matrix_routes_with_alias.update(
        (method, path.replace("{id}", "{pack_id}"))
        for method, path in matrix_routes
        if "{id}" in path
    )
    eco_routes = _core_ecosystem_routes()
    assert eco_routes.issubset(matrix_routes_with_alias)
