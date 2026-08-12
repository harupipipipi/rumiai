from __future__ import annotations

import importlib.util
import json
import re
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
TOOLCHAIN_BINDER = ROOT / ".github" / "scripts" / "packaging_toolchain_identity.py"
PACK_SHELL_SEALER = ROOT / ".github" / "scripts" / "seal_pack_shell.py"
UPDATER = TAURI_ROOT / "src" / "updater.rs"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
BUILD_AND_SIGN = ROOT / "scripts" / "build-and-sign.sh"
MACOS_CONFIG = TAURI_ROOT / "tauri.macos.conf.json"
MACOS_DEV_CONFIG = TAURI_ROOT / "tauri.macos.dev.conf.json"
MACOS_RELEASE_VERIFIER = ROOT / "tobkiri_launcher" / "scripts" / "verify_macos_release.sh"
MACOS_DMG_PACKAGER = ROOT / "tobkiri_launcher" / "scripts" / "package_macos_dmg.sh"
RELEASE_GATE = ROOT / "scripts" / "release_gate.py"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
DEV_REQUIREMENTS = ROOT / "tobkiri_runtime" / "requirements-dev.txt"
DEV_PYPROJECT = ROOT / "tobkiri_runtime" / "pyproject.toml"
VIEWER_BUILD_WORKFLOWS = (
    ROOT / ".github" / "workflows" / "desktop-installers.yml",
    ROOT / ".github" / "workflows" / "release.yml",
)
BUILD_RS = TAURI_ROOT / "build.rs"
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
        build_contents = contents.split("\n  gather:", 1)[0]
        assert "cargo tauri build" in build_contents
        assert "Prepare bundled Rumi runtime" not in build_contents
        assert "python .github/scripts/prepare_tauri_resources.py" not in build_contents
        prepare_at = build_contents.index(
            "Prepare sealed Python environment and export manifest binding"
        )
        cargo_positions = [
            match.start() for match in re.finditer(r"cargo tauri build", build_contents)
        ]
        assert cargo_positions and all(position > prepare_at for position in cargo_positions)
        assert "TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256" in build_contents
        assert ".github/scripts/prepare_tauri_resources.py" in build_contents
        assert "--check" in build_contents
        assert "--env-output" in build_contents
        assert "Bind verified packaging tool identities" in build_contents
        assert "TOBKIRI_PACKAGING_PYTHON" in build_contents
        assert "TOBKIRI_PACKAGING_PYTHON_SHA256" in build_contents
        assert "TOBKIRI_PACKAGING_GIT" in build_contents
        assert "TOBKIRI_PACKAGING_GIT_SHA256" in build_contents
        assert "aarch64-apple-darwin" in build_contents
        assert "x86_64-apple-darwin" in build_contents
        for forbidden in (
            "windows-latest",
            "ubuntu-latest",
            "x86_64-pc-windows-msvc",
            "x86_64-unknown-linux-gnu",
            "Upload Windows",
            "Upload Linux",
            "Sign and verify Windows installer",
        ):
            assert forbidden not in build_contents


def test_rust_packaging_callers_require_formal_absolute_tool_identities():
    """Rust release/build callers cannot fall back to ambient tools."""
    build = BUILD_RS.read_text(encoding="utf-8")
    assert TOOLCHAIN_BINDER.is_file()
    assert "packaging_toolchain.rs" in build
    assert "verified_tool_executable(\"python\")" in build
    assert "verified_tool_executable(\"git\")" in build
    assert "scripts.generator_source_manifest" in build
    assert "source closure failed before isolated generation" in build
    assert 'Command::new("git")' not in build
    assert 'var_os("PYTHON")' not in build
    assert 'unwrap_or_else(|| "python"' not in build


def test_macos_installer_uses_finder_free_verified_dmg_packager():
    assert MACOS_DMG_PACKAGER.is_file()
    packager = MACOS_DMG_PACKAGER.read_text(encoding="utf-8")
    for required in (
        "codesign --verify --deep --strict",
        "ditto",
        "command -v plutil",
        "ln -s /Applications",
        "hdiutil create",
        "hdiutil info",
        "hdiutil detach",
        "-fs APFS",
        "-format UDZO",
        'mktemp -d "$output_dir/.tobkiri-dmg.XXXXXX"',
        "owned_image_paths",
        "Resource busy",
        "trap cleanup EXIT",
        "trap 'exit 130' INT",
        "trap 'exit 143' TERM",
        'ln "$source_path" "$dmg_path"',
        "hdiutil verify",
        "unsafe version for a DMG filename",
    ):
        assert required in packager
    assert "-ov" not in packager
    assert "osascript" not in packager
    assert "bundle_dmg.sh" not in packager

    desktop_workflow = (
        ROOT / ".github" / "workflows" / "desktop-installers.yml"
    ).read_text(encoding="utf-8")
    desktop_macos = desktop_workflow[
        desktop_workflow.index("Build local macOS application (ad-hoc)") :
    ]
    assert "--bundles app" in desktop_macos
    assert "scripts/package_macos_dmg.sh" in desktop_macos
    assert "2>&1 | tee" in desktop_macos
    assert "--target '${{ matrix.target }}'" in desktop_macos

    release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    release_macos = release_workflow[
        release_workflow.index("Build signed macOS application") :
    ]
    assert "--bundles app" in release_macos
    assert "scripts/package_macos_dmg.sh" in release_macos
    assert "2>&1 | tee" in release_macos

    for workflow in (desktop_workflow, release_workflow):
        assert "Capture macOS installer diagnostics" in workflow
        assert "hdiutil info || true" in workflow


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
        (
            RELEASE_WORKFLOW,
            "Build debug Pack Shell for release Rust tests",
            "Seal debug Pack Shell for release Rust tests",
            "Run Rust release smoke tests",
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


def test_release_pack_shell_rebuilds_from_empty_or_cached_targets_and_seals_both_profiles():
    contents = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    clean_at = contents.index("Clean cached Pack Shell outputs before verified build")
    debug_build_at = contents.index("Build debug Pack Shell for release Rust tests")
    debug_seal_at = contents.index("Seal debug Pack Shell for release Rust tests")
    rust_test_at = contents.index("Run Rust release smoke tests")
    release_build_at = contents.index("Build release Pack Shell for verified Tauri Shell artifact")
    release_seal_at = contents.index("Seal release Pack Shell for verified Tauri Shell artifact")
    shell_build_at = contents.index("Build verified Tauri Shell artifact")

    assert clean_at < debug_build_at < debug_seal_at < rust_test_at
    assert rust_test_at < release_build_at < release_seal_at < shell_build_at
    assert "cargo clean --manifest-path pack-shell/Cargo.toml --target" in contents
    assert "cargo build --locked --manifest-path pack-shell/Cargo.toml" in contents
    assert "cargo build --release --locked --manifest-path pack-shell/Cargo.toml" in contents
    assert "--profile debug" in contents
    assert "--profile release" in contents
    assert "cache-hit" not in contents

    sealer = PACK_SHELL_SEALER.read_text(encoding="utf-8")
    preparer = RESOURCE_PREPARER.read_text(encoding="utf-8")
    assert "seal_pack_shell_binary" in sealer
    assert "pack_shell_digest_path" in preparer
    assert "hashlib.sha256(payload)" in preparer
    assert "sha256" in preparer


def test_updater_origin_matches_the_release_workflow_and_rejects_legacy_repository():
    updater = UPDATER.read_text(encoding="utf-8")
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    repository = re.search(
        r"TOBKIRI_RELEASE_REPOSITORY:\s*([^\s]+)", workflow
    )
    assert repository is not None
    assert repository.group(1) == "harupipipipi/tobkiri"
    assert 'RELEASE_REPOSITORY: &str = "harupipipipi/tobkiri"' in updater
    assert "https://api.github.com/repos/harupipipipi/tobkiri/releases/latest" in updater
    runtime_source = updater.split("#[cfg(test)]", 1)[0]
    assert "rumiai" not in runtime_source.lower()
    assert "repository=\"$(printf '%s' \"$GITHUB_REPOSITORY\" | tr '[:upper:]' '[:lower:]')\"" in workflow
    assert "expected=\"$(printf '%s' \"$TOBKIRI_RELEASE_REPOSITORY\" | tr '[:upper:]' '[:lower:]')\"" in workflow


def test_build_and_sign_rebuilds_canonical_defaultspack_before_staging():
    helper = BUILD_AND_SIGN.read_text(encoding="utf-8")
    build_at = helper.index("npm run build")
    check_at = helper.index("npm run check:shell-bundle")
    stage_at = helper.index("prepare_viewer_runtime.py")
    tauri_builds = [
        match.start() for match in re.finditer(r"cargo tauri build", helper)
    ]
    assert build_at < check_at < stage_at
    assert tauri_builds and all(position > stage_at for position in tauri_builds)
    assert "DEFAULTSPACK_WEBAPP_ROOT" in helper


def test_release_platform_signing_is_fail_closed_and_ad_hoc_is_dev_only():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    release_gate = RELEASE_GATE.read_text(encoding="utf-8")
    verifier = MACOS_RELEASE_VERIFIER.read_text(encoding="utf-8")
    mac_config = _read_json(MACOS_CONFIG)
    dev_config = _read_json(MACOS_DEV_CONFIG)

    for required in (
        "APPLE_CERTIFICATE_BASE64",
        "APPLE_CERTIFICATE_PASSWORD",
        "APPLE_SIGNING_IDENTITY",
        "APPLE_ID",
        "APPLE_APP_SPECIFIC_PASSWORD",
        "APPLE_TEAM_ID",
        "scripts/release_gate.py sign-artifacts",
    ):
        assert required in workflow

    for required in (
        "signtool.exe",
        '"sign"',
        '"verify"',
        '"notarytool"',
        '"stapler"',
        '"spctl"',
        '"ditto"',
    ):
        assert required in release_gate

    for required in (
        "Developer ID Application: ",
        "codesign --verify --deep --strict",
        "codesign --display --verbose=4",
        "Authority=-",
    ):
        assert required in verifier

    assert mac_config["bundle"]["targets"] == ["dmg"]
    assert "signingIdentity" not in mac_config["bundle"].get("macOS", {})
    assert dev_config["bundle"]["macOS"]["signingIdentity"] == "-"
    assert "tauri.macos.dev.conf.json" not in workflow
    desktop_workflow = (
        ROOT / ".github" / "workflows" / "desktop-installers.yml"
    ).read_text(encoding="utf-8")
    assert "--config src-tauri/tauri.macos.dev.conf.json" in desktop_workflow
    assert "--allow-ad-hoc-local" in desktop_workflow
    assert "--allow-ad-hoc-local" not in workflow

    verify_at = workflow.index("Verify Developer ID signed macOS application")
    dmg_at = workflow.index("Build macOS DMG installer")
    notarize_at = workflow.index("Notarize and staple macOS release DMG")
    upload_at = workflow.index("Upload one reviewable draft release")
    assert verify_at < dmg_at < notarize_at < upload_at
    assert "WINDOWS_CERTIFICATE_BASE64" not in workflow
    assert "WINDOWS_CERTIFICATE_PASSWORD" not in workflow
    assert "Sign and verify Windows installer" not in workflow
    assert "Linux" not in workflow
    assert {"aarch64-apple-darwin", "x86_64-apple-darwin"} <= set(
        re.findall(r"(?:aarch64|x86_64)-apple-darwin", workflow)
    )


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
