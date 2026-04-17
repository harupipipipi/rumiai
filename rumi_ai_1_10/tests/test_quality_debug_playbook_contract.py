from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "rumi_ai_1_10"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_contains_all(text: str, needles: list[str], context: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    assert not missing, f"{context} missing: {missing}"


def test_debug_playbook_contains_required_debug_sections():
    playbook = PACKAGE_ROOT / "docs" / "quality_pack" / "debug_playbook.md"
    assert playbook.exists()

    text = _read(playbook)
    _assert_contains_all(
        text,
        [
            "失敗層の特定",
            "ゲート別の最小再現コマンド",
            "典型デバッグ（frontend-lint）",
            "典型デバッグ（Python lint/type）",
            "セキュリティ/監査系の確認",
            "修正完了条件",
            ".quality_logs",
            "summary.txt",
            "manual_regression_scenarios*.yaml",
        ],
        "debug_playbook.md",
    )


def test_debug_bundle_script_covers_expected_gates():
    script = PACKAGE_ROOT / "scripts" / "quality_pack" / "run_debug_bundle.sh"
    assert script.exists()

    text = _read(script)
    _assert_contains_all(
        text,
        [
            "tests/test_entrypoint_contracts.py",
            "tests/test_claude_quality_pack_contract.py",
            "tests/test_quality_debug_playbook_contract.py",
            "tests/test_manual_regression_scenarios_contract.py",
            "tests/test_api_route_coverage_matrix_contract.py",
            "npm run lint",
            "npm run build",
            "cargo test",
        ],
        "run_debug_bundle.sh",
    )
