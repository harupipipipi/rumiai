from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TAURI_ROOT = ROOT / "rumi_viewer" / "src-tauri"
TAURI_CONFIG = TAURI_ROOT / "tauri.conf.json"
RESOURCE_PREPARER = ROOT / ".github" / "scripts" / "prepare_tauri_resources.py"
DEV_REQUIREMENTS = ROOT / "rumi_ai_1_10" / "requirements-dev.txt"
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
        "rumi_viewer/scripts/prepare_viewer_runtime.py --mode dev"
        in config["build"]["beforeDevCommand"]
    )
    assert (
        "rumi_viewer/scripts/prepare_viewer_runtime.py --mode release"
        in config["build"]["beforeBuildCommand"]
    )


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


def test_dev_uv_version_matches_release_bundle_pin():
    preparer = _load_resource_preparer()
    requirements = DEV_REQUIREMENTS.read_text(encoding="utf-8").splitlines()

    assert f"uv=={preparer.UV_PINNED_VERSION}" in requirements
