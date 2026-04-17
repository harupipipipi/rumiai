from __future__ import annotations

import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "rumi_ai_1_10"
QUALITY_PACK_DIR = PACKAGE_ROOT / "docs" / "quality_pack"
MATRIX_PATH = QUALITY_PACK_DIR / "viewer_release_contract_matrix.yaml"
SCENARIO_FILES = sorted(QUALITY_PACK_DIR.glob("manual_regression_scenarios*.yaml"))

REQUIRED_SECTIONS = {
    "viewer_runtime_contracts",
    "viewer_security_contracts",
    "release_pipeline_contracts",
    "ci_boundary_contracts",
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


def _assert_contract_shape(section: dict, clauses_key: str) -> None:
    assert isinstance(section.get("required_files"), list)
    assert isinstance(section.get(clauses_key), list)
    assert isinstance(section.get("manual_scenarios"), list)
    assert isinstance(section.get("automated_tests"), list)
    assert len(section["required_files"]) >= 3
    assert len(section[clauses_key]) >= 6
    assert len(section["manual_scenarios"]) >= 6
    assert len(section["automated_tests"]) >= 2


def test_viewer_release_contract_matrix_exists_and_has_required_sections():
    assert MATRIX_PATH.exists()
    matrix = _load_matrix()
    assert matrix.get("owner") == "quality-pack"
    assert isinstance(matrix.get("description"), str)
    assert REQUIRED_SECTIONS.issubset(set(matrix))


def test_viewer_release_contract_matrix_section_shapes():
    matrix = _load_matrix()
    _assert_contract_shape(matrix["viewer_runtime_contracts"], "required_behaviors")
    _assert_contract_shape(matrix["viewer_security_contracts"], "required_behaviors")
    _assert_contract_shape(matrix["release_pipeline_contracts"], "required_clauses")
    _assert_contract_shape(matrix["ci_boundary_contracts"], "required_clauses")


def test_viewer_release_contract_matrix_references_existing_files_and_tests():
    matrix = _load_matrix()
    all_files: list[str] = []
    all_tests: list[str] = []

    for section_name in REQUIRED_SECTIONS:
        section = matrix[section_name]
        all_files.extend(section["required_files"])
        all_tests.extend(section["automated_tests"])

    for rel in all_files:
        assert (REPO_ROOT / rel).exists(), f"missing required file: {rel}"

    for test_ref in all_tests:
        test_file = test_ref.split("::", 1)[0]
        assert (REPO_ROOT / test_file).exists(), f"missing test file: {test_file}"


def test_viewer_release_contract_matrix_manual_scenarios_exist():
    scenario_ids = _collect_scenario_ids()
    matrix = _load_matrix()
    for section_name in REQUIRED_SECTIONS:
        for scenario_id in matrix[section_name]["manual_scenarios"]:
            assert isinstance(scenario_id, str)
            assert scenario_id in scenario_ids, f"unknown scenario id: {scenario_id}"


def test_viewer_runtime_and_security_signatures():
    splash = (REPO_ROOT / "rumi_viewer/src-tauri/splash/index.html").read_text(encoding="utf-8")
    lib_rs = (REPO_ROOT / "rumi_viewer/src-tauri/src/lib.rs").read_text(encoding="utf-8")
    health = (REPO_ROOT / "rumi_viewer/src-tauri/src/health_check.rs").read_text(encoding="utf-8")
    kernel_manager = (REPO_ROOT / "rumi_viewer/src-tauri/src/kernel_manager.rs").read_text(
        encoding="utf-8"
    )
    tauri_conf = json.loads(
        (REPO_ROOT / "rumi_viewer/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    )
    viewer_cap = json.loads(
        (REPO_ROOT / "rumi_viewer/src-tauri/capabilities/default.json").read_text(encoding="utf-8")
    )

    assert "Initializing..." in splash
    assert "progress error" in splash
    assert "window.__TAURI__.core.invoke('get_setup_progress')" in splash

    assert "#[tauri::command]" in lib_rs
    assert "restart_kernel" in lib_rs
    assert "Blocked navigation to:" in lib_rs
    assert "window.location.replace('http://localhost:" in lib_rs

    assert "http://localhost:{port}/health" in health
    assert "MAX_AUTO_RESTARTS" in kernel_manager
    assert "kernel.log" in kernel_manager

    csp = tauri_conf["app"]["security"]["csp"]
    assert "http://localhost:8765" in csp
    assert "connect-src" in csp
    assert "https://" not in csp
    assert "*." not in csp
    assert tauri_conf["build"]["frontendDist"] == "./splash"
    assert tauri_conf["app"]["windows"][0]["visible"] is False

    assert "core:default" in viewer_cap["permissions"]
    assert "shell:allow-open" in viewer_cap["permissions"]


def test_release_and_ci_boundary_signatures():
    release_workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    test_workflow = (REPO_ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    quality_script = (
        REPO_ROOT / "rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh"
    ).read_text(encoding="utf-8")
    debug_script = (REPO_ROOT / "rumi_ai_1_10/scripts/quality_pack/run_debug_bundle.sh").read_text(
        encoding="utf-8"
    )

    for needle in [
        "tags:",
        '- "v*"',
        "aarch64-apple-darwin",
        "x86_64-apple-darwin",
        "x86_64-pc-windows-msvc",
        "x86_64-unknown-linux-gnu",
        "cargo tauri build --target",
        "softprops/action-gh-release@v2",
        "generate_release_notes: true",
    ]:
        assert needle in release_workflow

    for needle in [
        "root-python-tests",
        "rumi-ai-package-pytest",
        "rust-test",
        "pytest tests/ -v",
        "cd pack-shell && cargo test",
    ]:
        assert needle in test_workflow

    assert "tests/test_viewer_release_contract_matrix_contract.py" in quality_script
    assert "tests/test_viewer_release_contract_matrix_contract.py" in debug_script
