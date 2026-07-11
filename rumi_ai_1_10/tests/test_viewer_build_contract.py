from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TAURI_CONFIG = ROOT / "rumi_viewer" / "src-tauri" / "tauri.conf.json"
RESOURCE_PREPARER = ROOT / ".github" / "scripts" / "prepare_tauri_resources.py"
DEV_REQUIREMENTS = ROOT / "rumi_ai_1_10" / "requirements-dev.txt"


def _load_resource_preparer():
    spec = importlib.util.spec_from_file_location("prepare_tauri_resources", RESOURCE_PREPARER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {RESOURCE_PREPARER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tauri_hooks_prepare_runtime_for_dev_and_release():
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))

    assert "rumi_viewer/scripts/prepare_viewer_runtime.py --mode dev" in config["build"]["beforeDevCommand"]
    assert "rumi_viewer/scripts/prepare_viewer_runtime.py --mode release" in config["build"]["beforeBuildCommand"]


def test_default_bundle_targets_exclude_msi_for_prerelease_versions():
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))

    assert config["bundle"]["targets"] == ["dmg", "nsis", "deb", "appimage"]
    assert "msi" not in config["bundle"]["targets"]


def test_dev_uv_version_matches_release_bundle_pin():
    preparer = _load_resource_preparer()
    requirements = DEV_REQUIREMENTS.read_text(encoding="utf-8").splitlines()

    assert f"uv=={preparer.UV_PINNED_VERSION}" in requirements
