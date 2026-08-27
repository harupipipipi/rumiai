from __future__ import annotations

import importlib.util
import plistlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tobkiri_launcher/scripts/verify_macos_dmg_launch.py"
WORKFLOW = ROOT / ".github/workflows/release.yml"


def _load_script():
    """Load the standalone final-DMG verifier as an isolated test module."""
    spec = importlib.util.spec_from_file_location("verify_macos_dmg_launch", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = _load_script()


def _write_bundle(root: Path) -> Path:
    """Create a minimal production-identity app bundle for metadata tests."""
    app = root / VERIFY.APP_NAME
    executable = app / "Contents" / "MacOS" / "tobkiri-launcher"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"launcher")
    executable.chmod(0o755)
    with (app / "Contents" / "Info.plist").open("wb") as output:
        plistlib.dump(
            {
                "CFBundleIdentifier": VERIFY.BUNDLE_IDENTIFIER,
                "CFBundleExecutable": "tobkiri-launcher",
            },
            output,
        )
    return app


def test_final_dmg_verifier_validates_production_bundle_identity(tmp_path: Path) -> None:
    app = _write_bundle(tmp_path)

    assert VERIFY._validate_application_bundle(app) == {
        "bundle_identifier": VERIFY.BUNDLE_IDENTIFIER,
        "executable": "tobkiri-launcher",
    }


def test_final_dmg_verifier_rejects_nonproduction_bundle(tmp_path: Path) -> None:
    app = _write_bundle(tmp_path)
    app.rename(tmp_path / "Tobkiri Launcher CI E2E.app")

    with pytest.raises(VERIFY.DmgLaunchVerificationError, match="production"):
        VERIFY._validate_application_bundle(tmp_path / "Tobkiri Launcher CI E2E.app")


def test_final_dmg_verifier_uses_active_target_and_visible_ui_probe() -> None:
    assert VERIFY.ACTIVE_RELEASE_TARGETS == ("aarch64-apple-darwin",)
    with pytest.raises(VERIFY.DmgLaunchVerificationError, match="not active"):
        VERIFY._validate_target("x86_64-apple-darwin")
    assert "System Events" in VERIFY.VISIBLE_UI_APPLESCRIPT
    assert "visible is true" in VERIFY.VISIBLE_UI_APPLESCRIPT
    assert "count of windows" in VERIFY.VISIBLE_UI_APPLESCRIPT


def test_release_workflow_smokes_the_final_dmg_after_notarization() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    notarize = workflow.index("Notarize and staple macOS release DMG")
    launch = workflow.index("Launch final macOS DMG through LaunchServices")
    clean = workflow.index("Inspect post-build checkout cleanliness")
    upload = workflow.index("Prepare immutable target release upload")

    assert notarize < launch < clean < upload
    assert "scripts/verify_macos_dmg_launch.py" in workflow
    assert '--dmg "$dmg"' in workflow
    assert "--target '${{ matrix.target }}'" in workflow
    assert "--timeout-seconds 90" in workflow


def test_final_dmg_verifier_mounts_copies_and_launches_via_system_tools() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "MountedDmg" in source
    assert '"--rsrc", "--extattr", "--acl"' in source
    assert '"-n", os.fspath(copied_app)' in source
    assert '"/usr/bin") / name' in source
    assert "mount.verify_mounted()" in source
    assert "_wait_for_visible_ui" in source
