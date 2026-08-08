from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
TAURI_ROOT = ROOT / "tobkiri_launcher" / "src-tauri"
TAURI_CONFIG = TAURI_ROOT / "tauri.conf.json"
SHELL_TAURI_CONFIG = TAURI_ROOT / "tauri.shell.conf.json"
SHELL_RUNTIME = TAURI_ROOT / "src" / "shell_runtime.rs"
LAUNCHER_RUNTIME = TAURI_ROOT / "src" / "lib.rs"
RESOURCE_PREPARER = ROOT / ".github" / "scripts" / "prepare_tauri_resources.py"
PACK_SHELL_SEALER = ROOT / ".github" / "scripts" / "seal_pack_shell.py"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
DEV_REQUIREMENTS = ROOT / "tobkiri_runtime" / "requirements-dev.txt"
DEV_PYPROJECT = ROOT / "tobkiri_runtime" / "pyproject.toml"
VIEWER_BUILD_WORKFLOWS = (
    ROOT / ".github" / "workflows" / "desktop-installers.yml",
    ROOT / ".github" / "workflows" / "release.yml",
)
PLATFORM_TARGETS = {
    "windows": ["nsis"],
    "macos": ["dmg"],
    "linux": ["deb", "appimage"],
}


def _load_resource_preparer():
    spec = importlib.util.spec_from_file_location("prepare_tauri_resources", RESOURCE_PREPARER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {RESOURCE_PREPARER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_tauri_hooks_prepare_runtime_for_dev_and_release():
    config = _read_json(TAURI_CONFIG)

    assert (
        "tobkiri_launcher/scripts/prepare_viewer_runtime.py --mode dev"
        in config["build"]["beforeDevCommand"]
    )
    assert (
        "tobkiri_launcher/scripts/prepare_viewer_runtime.py --mode release"
        in config["build"]["beforeBuildCommand"]
    )


def test_shell_runtime_is_presentation_only_and_cannot_inherit_launcher_authority():
    shell_config = _read_json(SHELL_TAURI_CONFIG)
    assert shell_config["identifier"] == "io.tobkiri.shell.tauri"
    assert shell_config["mainBinaryName"] == "tobkiri-shell"
    assert shell_config["app"]["withGlobalTauri"] is False
    assert shell_config["app"]["trayIcon"] is None
    assert shell_config["bundle"]["resources"] is None
    assert shell_config["build"]["beforeBuildCommand"] is None
    assert shell_config["build"]["beforeDevCommand"] is None

    shell_runtime = SHELL_RUNTIME.read_text(encoding="utf-8")
    for forbidden in (
        "HostBrokerRuntime",
        "KernelManager",
        "DefaultspackManager",
        "invoke_handler",
        "tray::",
    ):
        assert forbidden not in shell_runtime
    assert "consume_shell_handoff" in shell_runtime
    assert "navigation_is_allowed" in shell_runtime

    launcher_runtime = LAUNCHER_RUNTIME.read_text(encoding="utf-8")
    assert "context.config().identifier == shell_handoff::SHELL_BUNDLE_IDENTIFIER" in launcher_runtime
    assert "shell_runtime::run(context)" in launcher_runtime
    assert "run_launcher(context)" in launcher_runtime


def test_installer_targets_are_selected_by_tauri_platform_overrides():
    base_config = _read_json(TAURI_CONFIG)
    assert base_config["bundle"]["targets"] == []

    for platform_name, expected_targets in PLATFORM_TARGETS.items():
        platform_config = _read_json(
            TAURI_ROOT / f"tauri.{platform_name}.conf.json"
        )
        targets = platform_config["bundle"]["targets"]
        assert targets == expected_targets
        assert "msi" not in targets


def test_ci_uses_tauri_as_the_single_release_preparation_entrypoint():
    for workflow in VIEWER_BUILD_WORKFLOWS:
        contents = workflow.read_text(encoding="utf-8")
        assert "cargo tauri build" in contents
        assert "Prepare bundled Rumi runtime" not in contents
        assert "python .github/scripts/prepare_tauri_resources.py" not in contents


def test_debug_pack_shell_is_built_and_sealed_before_launcher_rust_checks():
    assert PACK_SHELL_SEALER.is_file()
    expectations = (
        (
            ROOT / ".github" / "workflows" / "desktop-installers.yml",
            "Build debug Pack Shell for viewer Rust tests",
            "Seal debug Pack Shell for viewer Rust tests",
            "Run rumi viewer Rust tests",
        ),
        (
            TEST_WORKFLOW,
            "Build debug Pack Shell for viewer Rust checks",
            "Seal debug Pack Shell for viewer Rust checks",
            "Run rumi viewer tests",
        ),
    )
    for workflow, build_name, seal_name, test_name in expectations:
        contents = workflow.read_text(encoding="utf-8")
        build_at = contents.index(build_name)
        seal_at = contents.index(seal_name)
        test_at = contents.index(test_name)
        assert build_at < seal_at < test_at
        relevant = contents[build_at:test_at]
        assert "cargo build --locked --manifest-path pack-shell/Cargo.toml" in relevant
        assert "python .github/scripts/seal_pack_shell.py" in relevant
        assert "--profile debug" in relevant


def test_pack_shell_profile_is_a_single_safe_path_component():
    preparer = _load_resource_preparer()
    preparer._validate_profile_component("debug")
    preparer._validate_profile_component("release")

    for invalid in ("", ".", "..", "../debug", "debug/child", "debug\\child"):
        with pytest.raises(ValueError):
            preparer._validate_profile_component(invalid)


def test_dev_uv_version_matches_release_bundle_pin():
    preparer = _load_resource_preparer()
    pinned_requirement = f"uv=={preparer.UV_PINNED_VERSION}"
    requirements = DEV_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    pyproject = DEV_PYPROJECT.read_text(encoding="utf-8")

    assert any(line.startswith(pinned_requirement) for line in requirements)
    assert f'"{pinned_requirement}"' in pyproject
