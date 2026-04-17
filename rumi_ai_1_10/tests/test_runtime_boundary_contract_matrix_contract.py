from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "rumi_ai_1_10"
QUALITY_PACK_DIR = PACKAGE_ROOT / "docs" / "quality_pack"
MATRIX_PATH = QUALITY_PACK_DIR / "runtime_boundary_contract_matrix.yaml"
SCENARIO_FILES = sorted(QUALITY_PACK_DIR.glob("manual_regression_scenarios*.yaml"))

REQUIRED_SECTIONS = {
    "pack_api_boundary_contracts",
    "egress_boundary_contracts",
    "capability_proxy_boundary_contracts",
    "startup_active_ecosystem_contracts",
    "runtime_observability_contracts",
}

REQUIRED_SIGNATURES: dict[str, list[str]] = {
    "core_runtime/pack_api_server.py": [
        "def do_POST(self) -> None:",
        "if not self._check_rate_limit():",
        "if not _is_pre_auth_post and not self._check_auth():",
        'self._send_response(APIResponse(False, error="Unauthorized"), 401)',
    ],
    "core_runtime/egress_proxy.py": [
        'GENERIC_SECURITY_BLOCK_MESSAGE = "Request blocked by security policy"',
        "MAX_REDIRECTS = 3",
        "def _pack_socket_name(pack_id: str) -> str:",
        'DEFAULT_CONNECT_TIMEOUT = float(os.environ.get("RUMI_EGRESS_CONNECT_TIMEOUT", "10.0"))',
    ],
    "core_runtime/capability_proxy.py": [
        "def _principal_socket_name(principal_id: str) -> str:",
        "MAX_REQUEST_SIZE = 4 * 1024 * 1024",
        "def _apply_socket_permissions(sock_path: Path) -> None:",
        "_audit_transport_warning(",
    ],
    "app.py": [
        'parser.add_argument("--health", action="store_true", help="Run health check and exit with status")',
        "if args.permissive:",
        'os.environ.setdefault("RUMI_SECURITY_MODE", "strict")',
        "if args.health:",
    ],
    "backend_core/ecosystem/active_ecosystem.py": [
        "def _load_config(self):",
        "if not stored_sig:",
        "elif not verify_data_hmac(self._secret_key, data, stored_sig):",
        "def migrate_hmac_signature(self) -> str:",
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


def test_runtime_boundary_contract_matrix_exists_and_sections_present():
    assert MATRIX_PATH.exists()
    matrix = _load_matrix()
    assert matrix.get("owner") == "quality-pack"
    assert isinstance(matrix.get("summary"), str)
    assert REQUIRED_SECTIONS.issubset(set(matrix))


def test_runtime_boundary_contract_matrix_section_shapes():
    matrix = _load_matrix()
    for section_name in REQUIRED_SECTIONS:
        _assert_contract_shape(matrix[section_name])


def test_runtime_boundary_contract_matrix_references_existing_files_and_tests():
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


def test_runtime_boundary_contract_matrix_manual_scenarios_exist():
    scenario_ids = _collect_scenario_ids()
    matrix = _load_matrix()
    for section_name in REQUIRED_SECTIONS:
        for scenario_id in matrix[section_name]["key_manual_scenarios"]:
            assert isinstance(scenario_id, str)
            assert scenario_id in scenario_ids, f"unknown scenario id: {scenario_id}"


def test_runtime_boundary_contract_signatures_are_present():
    for rel_path, signatures in REQUIRED_SIGNATURES.items():
        text = (PACKAGE_ROOT / rel_path).read_text(encoding="utf-8")
        for signature in signatures:
            assert signature in text, f"missing signature in {rel_path}: {signature}"


def test_runtime_boundary_contract_quality_scripts_include_test():
    quality_script = (
        PACKAGE_ROOT / "scripts" / "quality_pack" / "run_claude_quality_pack.sh"
    ).read_text(encoding="utf-8")
    debug_script = (PACKAGE_ROOT / "scripts" / "quality_pack" / "run_debug_bundle.sh").read_text(
        encoding="utf-8"
    )

    assert "tests/test_runtime_boundary_contract_matrix_contract.py" in quality_script
    assert "tests/test_runtime_boundary_contract_matrix_contract.py" in debug_script
