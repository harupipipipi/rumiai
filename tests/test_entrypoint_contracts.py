import re
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_root_entrypoint_targets_legacy_app_main():
    entrypoint = _read(ROOT / "rumi_ai" / "__main__.py")
    cli_text = _read(ROOT / "rumi_ai" / "cli.py")

    assert "from .cli import main" in entrypoint
    assert 'runtime_root = repo_root / "rumi_ai_1_10"' in cli_text
    assert "from rumi_ai_1_10.app import main as runtime_main" in cli_text
    assert 'if __name__ == "__main__":' in entrypoint


def test_root_pyproject_installs_stable_entrypoint_package():
    root_pyproject = _read(ROOT / "pyproject.toml")
    readme_text = _read(ROOT / "README.md")
    contributing_text = _read(ROOT / "CONTRIBUTING.md")
    workflow_text = _read(ROOT / ".github" / "workflows" / "test.yml")
    first_run_text = _read(ROOT / "docs" / "first-run-check.md")
    justfile_text = _read(ROOT / "justfile")
    package_smoke_text = _read(ROOT / "scripts" / "check_package_install.py")

    assert 'name = "rumi-ai"' in root_pyproject
    assert '"rumi_ai*"' in root_pyproject
    assert '"rumi_ai_1_10*"' in root_pyproject
    assert 'rumi-ai = "rumi_ai.cli:main"' in root_pyproject
    assert 'pip install -e ".[dev]"' in readme_text
    assert 'pip install -e ".[dev]"' in contributing_text
    assert "pip install -e ." in first_run_text
    assert "rumi-ai --health" in first_run_text
    assert 'cd "$RUNNER_TEMP"' in workflow_text
    assert "python -m rumi_ai --health" in workflow_text
    assert "rumi-ai --health" in workflow_text
    assert "python scripts/check_package_install.py" in first_run_text
    assert "just package-smoke" in first_run_text
    assert "package-smoke:" in justfile_text
    assert '"pip", "wheel"' in package_smoke_text
    assert "outside-checkout" in package_smoke_text


def test_version_contract_matches_package_version():
    init_text = _read(ROOT / "rumi_ai" / "__init__.py")
    pyproject_text = _read(ROOT / "rumi_ai_1_10" / "pyproject.toml")

    init_match = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    pyproject_match = re.search(
        r'^\s*version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE
    )

    assert init_match, "rumi_ai.__version__ not found"
    assert pyproject_match, "project.version in pyproject.toml not found"
    assert init_match.group(1) == pyproject_match.group(1)


def test_control_panel_bundle_uses_v3_startup_profile_contract():
    web_root = ROOT / "rumi_ai_1_10" / "core_runtime" / "core_pack" / "core_control_panel" / "web"
    scripts = list((web_root / "assets").glob("*.js"))

    assert scripts, "control panel web bundle is missing"

    bundle_text = "\n".join(_read(script) for script in scripts)
    assert "base_pack" in bundle_text
    assert "standard_pack_id" not in bundle_text


def test_first_run_docs_keep_health_check_contract_visible():
    readme_text = _read(ROOT / "README.md")
    first_run_text = _read(ROOT / "docs" / "first-run-check.md")

    assert "docs/first-run-check.md" in readme_text
    assert "python -m rumi_ai --health" in first_run_text
    assert "just health" in first_run_text
    assert "tests/test_entrypoint_contracts.py" in first_run_text


def test_public_readiness_docs_keep_adoption_evidence_visible():
    readme_text = _read(ROOT / "README.md")
    launch_text = _read(ROOT / "docs" / "community-launch-plan.md")
    evidence_text = _read(ROOT / "docs" / "adoption-evidence.md")
    demo_text = _read(ROOT / "docs" / "demo-script.md")
    setup_template_text = _read(ROOT / ".github" / "ISSUE_TEMPLATE" / "setup_feedback.yml")

    assert "docs/adoption-evidence.md" in readme_text
    assert "docs/demo-script.md" in readme_text
    assert "setup_feedback.yml" in readme_text
    assert "adoption-evidence.md" in launch_text
    assert "demo-script.md" in launch_text
    assert "setup_feedback.yml" in launch_text
    assert "setup_feedback.yml" in evidence_text
    assert "Do not count:" in evidence_text
    assert "Bought stars" in evidence_text or "bought stars" in evidence_text
    assert "python -m rumi_ai --health" in demo_text
    assert "rumi-ai --health" in demo_text
    assert "python scripts/verify_oss_readiness.py" in demo_text
    assert "python scripts/check_package_install.py" in demo_text
    assert "python -m rumi_ai --health" in setup_template_text
    assert "remove secrets" in setup_template_text.lower()


def test_oss_readiness_verifier_passes():
    proc = subprocess.run(
        [sys.executable, "scripts/verify_oss_readiness.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "pass"
