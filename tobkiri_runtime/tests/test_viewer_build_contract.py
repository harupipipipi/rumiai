from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
TAURI_ROOT = ROOT / "tobkiri_launcher" / "src-tauri"
TAURI_CONFIG = TAURI_ROOT / "tauri.conf.json"
RESOURCE_PREPARER = ROOT / ".github" / "scripts" / "prepare_tauri_resources.py"
DEV_REQUIREMENTS = ROOT / "tobkiri_runtime" / "requirements-dev.txt"
DEV_PYPROJECT = ROOT / "tobkiri_runtime" / "pyproject.toml"
VIEWER_BUILD_WORKFLOWS = (
    ROOT / ".github" / "workflows" / "desktop-installers.yml",
    ROOT / ".github" / "workflows" / "release.yml",
)
MACOS_UNSIGNED_DISTRIBUTION_DOC = (
    ROOT / "tobkiri_runtime" / "docs" / "macos-unsigned-distribution.md"
)
PLATFORM_TARGETS = {
    "windows": ["nsis"],
    "macos": ["dmg"],
    "linux": ["deb", "appimage"],
}


def _workflow_job(path: Path) -> dict:
    """Return the matrix build job from a checked-in workflow."""
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = parsed.get("jobs")
    assert isinstance(jobs, dict)
    job = next(
        (
            value
            for value in jobs.values()
            if isinstance(value, dict)
            and isinstance(value.get("strategy"), dict)
            and isinstance(value["strategy"].get("matrix"), dict)
        ),
        None,
    )
    assert isinstance(job, dict)
    return job


def _load_resource_preparer():
    spec = importlib.util.spec_from_file_location(
        "prepare_tauri_resources", RESOURCE_PREPARER
    )
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


def test_installer_targets_are_selected_by_tauri_platform_overrides():
    base_config = _read_json(TAURI_CONFIG)
    assert base_config["bundle"]["targets"] == []

    for platform_name, expected_targets in PLATFORM_TARGETS.items():
        platform_config = _read_json(TAURI_ROOT / f"tauri.{platform_name}.conf.json")
        targets = platform_config["bundle"]["targets"]
        assert targets == expected_targets
        assert "msi" not in targets


def test_ci_uses_tauri_as_the_single_release_preparation_entrypoint():
    for workflow in VIEWER_BUILD_WORKFLOWS:
        contents = workflow.read_text(encoding="utf-8")
        assert "cargo tauri build" in contents
        assert "Prepare bundled Rumi runtime" not in contents
        assert "python .github/scripts/prepare_tauri_resources.py" not in contents


def test_macos_release_is_explicitly_unsigned_and_documents_constraints():
    for workflow in VIEWER_BUILD_WORKFLOWS:
        job = _workflow_job(workflow)
        matrix_rows = job["strategy"]["matrix"]["include"]
        macos_rows = [
            row for row in matrix_rows if row.get("os", "").startswith("macos")
        ]
        non_macos_rows = [
            row for row in matrix_rows if not row.get("os", "").startswith("macos")
        ]
        build_commands = [
            step["run"]
            for step in job["steps"]
            if "cargo tauri build" in str(step.get("run", ""))
        ]

        assert len(macos_rows) == 2
        assert all(row.get("signing_args") == "--no-sign" for row in macos_rows)
        assert all(not row.get("signing_args") for row in non_macos_rows)
        assert build_commands
        assert all(
            "${{ matrix.signing_args }}" in command for command in build_commands
        )

    documentation = MACOS_UNSIGNED_DISTRIBUTION_DOC.read_text(encoding="utf-8")
    for required_term in (
        "unsigned",
        "ad-hoc",
        "Developer ID",
        "Gatekeeper",
        "quarantine",
        "TCC",
        "dev.rumiai.app",
    ):
        assert required_term in documentation


def test_release_draft_notes_describe_unsigned_artifacts_without_auto_claims():
    job = _workflow_job(ROOT / ".github" / "workflows" / "release.yml")
    release_step = next(
        step
        for step in job["steps"]
        if "softprops/action-gh-release" in str(step.get("uses", ""))
    )
    release_notes = release_step["with"]

    assert release_notes["draft"] is True
    assert release_notes["generate_release_notes"] is True
    body = str(release_notes["body"])
    assert "unsigned/ad-hoc" in body
    assert "not Developer ID-signed" in body
    assert "notarized" in body


def test_dev_uv_version_matches_release_bundle_pin():
    preparer = _load_resource_preparer()
    pinned_requirement = f"uv=={preparer.UV_PINNED_VERSION}"
    requirements = DEV_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    pyproject = DEV_PYPROJECT.read_text(encoding="utf-8")

    assert pinned_requirement in requirements
    assert f'"{pinned_requirement}"' in pyproject
