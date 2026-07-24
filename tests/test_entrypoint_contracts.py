import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_root_compatibility_entrypoint_delegates_to_canonical_runtime():
    entrypoint = _read(ROOT / "rumi_ai" / "__main__.py")
    assert "_LEGACY_ROOT" in entrypoint
    assert "from tobkiri.runtime import main" in entrypoint
    assert "from tobkiri_runtime.app import main" not in entrypoint
    assert 'if __name__ == "__main__":' in entrypoint


def test_version_contract_matches_package_version():
    init_text = _read(ROOT / "rumi_ai" / "__init__.py")
    canonical_init_text = _read(ROOT / "tobkiri_runtime" / "tobkiri" / "__init__.py")
    pyproject_text = _read(ROOT / "tobkiri_runtime" / "pyproject.toml")

    init_match = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    pyproject_match = re.search(
        r'^\s*version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE
    )

    assert init_match, "rumi_ai.__version__ not found"
    assert pyproject_match, "project.version in pyproject.toml not found"
    assert init_match.group(1) == pyproject_match.group(1)
    assert f'__version__ = "{pyproject_match.group(1)}"' in canonical_init_text


def test_package_discovery_keeps_tobkiri_primary_and_legacy_temporarily():
    pyproject_text = _read(ROOT / "tobkiri_runtime" / "pyproject.toml")
    assert '"tobkiri*"' in pyproject_text
    assert '"rumi_ai*"' in pyproject_text
    assert "Canonical Tobkiri runtime package" in _read(
        ROOT / "tobkiri_runtime" / "tobkiri" / "__init__.py"
    )


def _module_command(
    module: str,
    cwd: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    runtime_root = str(ROOT / "tobkiri_runtime")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (runtime_root, env.get("PYTHONPATH", "")) if part
    )
    return subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_canonical_cli_works_outside_repository_and_legacy_help_matches(tmp_path):
    canonical = _module_command("tobkiri", tmp_path, "--help")
    legacy = _module_command("rumi_ai", tmp_path, "--help")

    assert canonical.returncode == 0, canonical.stderr
    assert legacy.returncode == canonical.returncode, legacy.stderr
    assert canonical.stdout == legacy.stdout
    assert "Tobkiri" in canonical.stdout
    assert "--health" in canonical.stdout
    assert "migrate-hmac" in canonical.stdout


def _normalized_health(result: subprocess.CompletedProcess[str]) -> dict:
    payload = json.loads(result.stdout)
    payload.pop("timestamp", None)
    for probe in payload.get("probes", {}).values():
        if isinstance(probe, dict):
            probe.pop("duration_ms", None)
    return payload


def test_canonical_and_installed_legacy_health_are_semantically_equivalent(tmp_path):
    canonical = _module_command("tobkiri", tmp_path, "--health")
    legacy = _module_command("rumi_ai", tmp_path, "--health")

    assert canonical.returncode in {0, 1}, canonical.stderr
    assert legacy.returncode == canonical.returncode, legacy.stderr
    assert canonical.stderr == legacy.stderr
    assert bool(canonical.stdout.strip()) == bool(legacy.stdout.strip())
    if canonical.stdout.strip():
        assert canonical.stderr == ""
        assert _normalized_health(canonical) == _normalized_health(legacy)
    else:
        assert canonical.stdout == legacy.stdout == ""
        assert "FATAL: Missing critical dependencies:" in canonical.stderr


def test_root_source_compatibility_shim_matches_canonical_help():
    canonical = _module_command("tobkiri", ROOT, "--help")
    root_legacy = _module_command("rumi_ai", ROOT, "--help")

    assert canonical.returncode == root_legacy.returncode == 0
    assert canonical.stdout == root_legacy.stdout
    assert canonical.stderr == root_legacy.stderr == ""


def test_active_callers_use_the_canonical_cli():
    assert "python -m tobkiri --health" in _read(ROOT / "justfile")
    assert 'DEFAULT_KERNEL_CMD: &str = "python -m tobkiri"' in _read(
        ROOT / "pack-shell" / "src" / "config.rs"
    )
    readme = _read(ROOT / "README.md")
    assert "python -m tobkiri --health" in readme
    assert "python -m tobkiri migrate-hmac" in readme

    active_docs = (
        ROOT / "pack-shell" / "README.md",
        ROOT / "tobkiri_mobile" / "README.md",
        ROOT / "tobkiri_runtime" / "README.md",
        ROOT / "tobkiri_runtime" / "docs" / "tutorials" / "runtime-quickstart.md",
        ROOT / "tobkiri_runtime" / "docs" / "pack_desktop_app_guide.md",
        ROOT / "tobkiri_runtime" / "docs" / "ci_build_guide.md",
    )
    for path in active_docs:
        text = _read(path)
        assert "python -m rumi_ai" not in text, path
        assert "github.com/harupipipipi/rumiai" not in text, path


def test_launcher_does_not_depend_on_the_legacy_python_shim():
    launcher_root = ROOT / "tobkiri_launcher"
    active_sources = (
        *launcher_root.joinpath("src-tauri", "src").glob("*.rs"),
        *launcher_root.joinpath("frontend", "src").rglob("*.ts"),
        *launcher_root.joinpath("frontend", "src").rglob("*.tsx"),
    )

    assert active_sources
    for path in active_sources:
        assert "python -m rumi_ai" not in _read(path), path


def test_remaining_legacy_cli_examples_are_explicit_compatibility_or_history():
    allowed = {
        Path("docs/tobkiri-internal-migration.md"),
        Path("tests/test_entrypoint_contracts.py"),
        Path("tobkiri_runtime/rumi_ai/__main__.py"),
        Path("tobkiri_runtime/docs/rumi_viewer_start.md"),
        Path("tobkiri_runtime/ecosystem/defaultspack/docs/competitive_agent_install_eval.md"),
    }
    matches = set()
    excluded_parts = {"node_modules", "dist", "target", ".git", ".venv"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in excluded_parts for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "python -m rumi_ai" in text:
            matches.add(path.relative_to(ROOT))

    assert matches == allowed


def test_active_guides_use_tobkiri_branding():
    active_guides = (
        ROOT / "tobkiri_runtime" / "README.md",
        ROOT / "tobkiri_runtime" / "docs" / "README.md",
        ROOT / "tobkiri_runtime" / "docs" / "architecture.md",
        ROOT / "tobkiri_runtime" / "docs" / "ci_build_guide.md",
        ROOT / "tobkiri_runtime" / "docs" / "concepts" / "system-mechanism.md",
        ROOT / "tobkiri_runtime" / "docs" / "multilang_pack_guide.md",
        ROOT / "tobkiri_runtime" / "docs" / "pack-development-guide.md",
        ROOT / "tobkiri_runtime" / "docs" / "pack-development.md",
        ROOT / "tobkiri_runtime" / "docs" / "pack_desktop_app_guide.md",
        ROOT / "tobkiri_runtime" / "docs" / "pack_development_guide.md",
        ROOT / "tobkiri_runtime" / "docs" / "examples" / "desktop_app_pack" / "README.md",
        ROOT / "tobkiri_runtime" / "docs" / "examples" / "viewer_hello_pack" / "README.md",
        ROOT / "tobkiri_runtime" / "docs" / "examples" / "viewer_pack" / "README.md",
    )
    for path in active_guides:
        text = _read(path)
        assert "Rumi AI" not in text, path
        assert "Rumi Viewer" not in text, path


def test_control_panel_bundle_uses_v3_startup_profile_contract():
    web_root = ROOT / "tobkiri_runtime" / "core_runtime" / "core_pack" / "core_control_panel" / "web"
    scripts = list((web_root / "assets").glob("*.js"))

    assert scripts, "control panel web bundle is missing"

    bundle_text = "\n".join(_read(script) for script in scripts)
    assert "base_pack" in bundle_text
    assert "standard_pack_id" not in bundle_text


def test_pack_architecture_entrypoint_targets_canonical_runtime():
    entrypoint = _read(ROOT / "scripts" / "quality" / "scan_pack_architecture.py")

    assert '"tobkiri_runtime"' in entrypoint
    assert '"rumi_ai_1_10"' not in entrypoint


def test_just_windows_shell_supports_existing_command_chains():
    justfile = _read(ROOT / "justfile")

    assert 'set windows-shell := ["cmd.exe", "/C"]' in justfile
    assert "powershell.exe" not in justfile
