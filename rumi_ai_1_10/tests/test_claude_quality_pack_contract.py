from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "rumi_ai_1_10"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_contains_all(text: str, needles: list[str], context: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    assert not missing, f"{context} missing: {missing}"


def test_quality_pack_docs_exist_and_have_required_sections():
    philosophy_memo = PACKAGE_ROOT / "docs" / "quality_pack" / "philosophy_memo.md"
    quality_pack = PACKAGE_ROOT / "docs" / "quality_pack" / "claude_desktop_quality_pack.md"

    assert philosophy_memo.exists()
    assert quality_pack.exists()

    memo_text = _read(philosophy_memo)
    pack_text = _read(quality_pack)

    _assert_contains_all(
        memo_text,
        [
            "No Favoritism",
            "Fail-Soft",
            "Malicious Pack assumption",
            "Quality standards",
            "Change judgment rules",
        ],
        "philosophy_memo.md",
    )

    _assert_contains_all(
        pack_text,
        [
            "Execution commands",
            "Audit Procedures",
            "Manual verification steps",
            "Regression confirmation procedure",
            "Pre-release check",
            "Ideology Compatibility Checklist",
            "Isolation procedure in case of failure",
            "AI agent operation prompt",
        ],
        "claude_desktop_quality_pack.md",
    )


def test_ci_workflows_keep_required_quality_gates():
    test_workflow = _read(REPO_ROOT / ".github" / "workflows" / "test.yml")
    release_workflow = _read(REPO_ROOT / ".github" / "workflows" / "release.yml")

    _assert_contains_all(
        test_workflow,
        [
            "root-python-tests",
            "rumi-ai-contract-checks",
            "rumi-ai-static-checks",
            "rumi-ai-package-pytest",
            "rust-test",
            "pytest tests/ -v",
            "pytest -m contract -v",
            "Run Ruff/mypy non-regression guard",
            "cd pack-shell && cargo test",
        ],
        ".github/workflows/test.yml",
    )

    _assert_contains_all(
        release_workflow,
        [
            "tags:",
            '- "v*"',
            "cargo tauri build --target",
        ],
        ".github/workflows/release.yml",
    )


def test_ui_security_and_frontend_contracts():
    tauri_conf = json.loads(_read(REPO_ROOT / "rumi_viewer" / "src-tauri" / "tauri.conf.json"))
    viewer_cap = json.loads(
        _read(REPO_ROOT / "rumi_viewer" / "src-tauri" / "capabilities" / "default.json")
    )
    frontend_package = json.loads(_read(REPO_ROOT / "rumi_viewer" / "frontend" / "package.json"))

    csp = tauri_conf["app"]["security"]["csp"]
    assert "http://localhost:8765" in csp
    assert "connect-src" in csp
    assert "https://" not in csp
    assert "*." not in csp

    assert viewer_cap["identifier"] == "default"
    assert "core:default" in viewer_cap.get("permissions", [])

    scripts = frontend_package["scripts"]
    assert "lint" in scripts
    assert scripts["lint"] == "tsc --noEmit"
    assert "build" in scripts
    assert "vite build" in scripts["build"]
