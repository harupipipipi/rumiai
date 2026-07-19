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


def _module_help(module: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    runtime_root = str(ROOT / "tobkiri_runtime")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (runtime_root, env.get("PYTHONPATH", "")) if part
    )
    return subprocess.run(
        [sys.executable, "-m", module, "--help"],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_canonical_cli_works_outside_repository_and_legacy_help_matches(tmp_path):
    canonical = _module_help("tobkiri", tmp_path)
    legacy = _module_help("rumi_ai", tmp_path)

    assert canonical.returncode == 0, canonical.stderr
    assert legacy.returncode == canonical.returncode, legacy.stderr
    assert canonical.stdout == legacy.stdout
    assert "Tobkiri" in canonical.stdout
    assert "--health" in canonical.stdout
    assert "migrate-hmac" in canonical.stdout


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


def test_control_panel_bundle_uses_v3_startup_profile_contract():
    web_root = ROOT / "tobkiri_runtime" / "core_runtime" / "core_pack" / "core_control_panel" / "web"
    scripts = list((web_root / "assets").glob("*.js"))

    assert scripts, "control panel web bundle is missing"

    bundle_text = "\n".join(_read(script) for script in scripts)
    assert "base_pack" in bundle_text
    assert "standard_pack_id" not in bundle_text
