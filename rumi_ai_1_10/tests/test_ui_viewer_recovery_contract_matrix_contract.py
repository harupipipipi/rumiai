from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "rumi_ai_1_10"
QUALITY_PACK_DIR = PACKAGE_ROOT / "docs" / "quality_pack"
MATRIX_PATH = QUALITY_PACK_DIR / "ui_viewer_recovery_contract_matrix.yaml"
SCENARIO_FILES = sorted(QUALITY_PACK_DIR.glob("manual_regression_scenarios*.yaml"))

REQUIRED_SECTIONS = {
    "frontend_interaction_contracts",
    "viewer_recovery_contracts",
    "pack_shell_bootstrap_contracts",
    "ui_failure_observability_contracts",
}

REQUIRED_SIGNATURES: dict[str, list[str]] = {
    "frontend/src/App.tsx": [
        '<BrowserRouter basename="/panel">',
        '<Route path="/setup" element={<Setup />} />',
        "<ToastContainer />",
        "<DialogContainer />",
    ],
    "frontend/src/components/ui/ErrorBoundary.tsx": [
        "class ErrorBoundary extends Component<Props, State>",
        "static getDerivedStateFromError(error: Error): State {",
        "componentDidCatch(error: Error, errorInfo: ErrorInfo): void {",
        "window.location.reload();",
    ],
    "../rumi_viewer/src-tauri/src/lib.rs": [
        "#[tauri::command]",
        "fn get_setup_progress(",
        "fn restart_kernel(",
        "Blocked navigation to:",
        "Startup update check failed (non-fatal):",
    ],
    "../rumi_viewer/src-tauri/src/kernel_manager.rs": [
        "const RESTART_EXIT_CODE: i32 = 42;",
        "const MAX_AUTO_RESTARTS: u32 = 3;",
        "pub fn wait_and_handle_restart(&mut self) -> Result<bool> {",
    ],
    "../pack-shell/src/main.rs": [
        "if !client.is_healthy() {",
        "wait_for_healthy(config.timeout)",
        "get_desktop_token(&config.pack_id)",
        '.env("RUMI_TOKEN", &token_response.token)',
        "Commands::Version => {",
    ],
    "../pack-shell/src/client.rs": [
        "pub fn is_healthy(&self) -> bool {",
        "pub fn wait_for_healthy(&self, timeout_secs: u64) -> Result<()> {",
        "pub fn get_desktop_token(&self, pack_id: &str) -> Result<DesktopToken> {",
        '.header("Authorization", format!("Bearer {}", self.api_token))',
    ],
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


def _assert_contract_shape(section: dict) -> None:
    assert isinstance(section.get("required_files"), list)
    assert isinstance(section.get("required_behaviors"), list)
    assert isinstance(section.get("key_manual_scenarios"), list)
    assert isinstance(section.get("automated_tests"), list)
    assert len(section["required_files"]) >= 4
    assert len(section["required_behaviors"]) >= 6
    assert len(section["key_manual_scenarios"]) >= 6
    assert len(section["automated_tests"]) >= 3


def test_ui_viewer_recovery_contract_matrix_exists_and_sections_present():
    assert MATRIX_PATH.exists()
    matrix = _load_matrix()
    assert matrix.get("owner") == "quality-pack"
    assert isinstance(matrix.get("summary"), str)
    assert REQUIRED_SECTIONS.issubset(set(matrix))


def test_ui_viewer_recovery_contract_matrix_section_shapes():
    matrix = _load_matrix()
    for section_name in REQUIRED_SECTIONS:
        _assert_contract_shape(matrix[section_name])


def test_ui_viewer_recovery_contract_matrix_references_existing_files_and_tests():
    matrix = _load_matrix()
    all_files: list[str] = []
    all_tests: list[str] = []
    for section_name in REQUIRED_SECTIONS:
        section = matrix[section_name]
        all_files.extend(section["required_files"])
        all_tests.extend(section["automated_tests"])

    for rel in all_files:
        assert (PACKAGE_ROOT / rel).exists() or (REPO_ROOT / rel).exists(), (
            f"missing required file: {rel}"
        )

    for test_ref in all_tests:
        test_file = test_ref.split("::", 1)[0]
        assert (REPO_ROOT / test_file).exists(), f"missing test file: {test_file}"


def test_ui_viewer_recovery_contract_matrix_manual_scenarios_exist():
    scenario_ids = _collect_scenario_ids()
    matrix = _load_matrix()
    for section_name in REQUIRED_SECTIONS:
        for scenario_id in matrix[section_name]["key_manual_scenarios"]:
            assert isinstance(scenario_id, str)
            assert scenario_id in scenario_ids, f"unknown scenario id: {scenario_id}"


def test_ui_viewer_recovery_contract_signatures_are_present():
    for rel_path, signatures in REQUIRED_SIGNATURES.items():
        text = (PACKAGE_ROOT / rel_path).read_text(encoding="utf-8")
        for signature in signatures:
            assert signature in text, f"missing signature in {rel_path}: {signature}"


def test_ui_viewer_recovery_contract_quality_scripts_include_test():
    quality_script = (
        PACKAGE_ROOT / "scripts" / "quality_pack" / "run_claude_quality_pack.sh"
    ).read_text(encoding="utf-8")
    debug_script = (PACKAGE_ROOT / "scripts" / "quality_pack" / "run_debug_bundle.sh").read_text(
        encoding="utf-8"
    )

    assert "tests/test_ui_viewer_recovery_contract_matrix_contract.py" in quality_script
    assert "tests/test_ui_viewer_recovery_contract_matrix_contract.py" in debug_script
