"""Regression tests for final generated closure re-sealing."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
BUILDER_PATH = ROOT / ".github/scripts/build_sealed_python_environment.py"
FIXTURE_PATH = ROOT / "tobkiri_runtime/tests/test_sealed_python_environment.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load(BUILDER_PATH, "sealed_application_closure_builder")
FIXTURES = _load(FIXTURE_PATH, "sealed_application_closure_fixtures")


def _packaged_application_closure(base: Path) -> Path:
    app = base / "packaged-app"
    artifact_id = "shell.fixture.default.linux-x86_64"
    digest = "sha256:" + "7" * 64
    artifact_ref = "fixture-shell"
    files = {
        "bundled/presentation_catalog.json": {
            "shell_providers": [{
                "provider_id": "shell.fixture.default",
                "artifact_variants": [{"artifact_id": artifact_id, "sha256": digest}],
            }]
        },
        "bundled/presentation_release.v4.json": {"artifact_id": artifact_id},
        "bundled/shell_artifact_index.v4.json": {
            "artifact_id": artifact_id,
            "sha256": digest,
            "path": "bundled/presentation-artifacts/fixture/fixture-shell",
        },
        "bundled/shell_profile_lock.v4.json": {"artifact_id": artifact_id},
        "ecosystem/defaultspack/pack.v4.json": {"pack_id": "defaultspack"},
        "ecosystem/defaultspack/contracts.v4.json": {"contracts": []},
        "ecosystem/defaultspack/artifact-index.v4.json": {"artifacts": []},
        "ecosystem/defaultspack/executables.v4.json": {"executables": []},
        "ecosystem/defaultspack/v4/defaults.profile.v4.json": {"profile_id": "defaults"},
        "ecosystem/defaultspack/v4/bundle.lock.json": {"entries": []},
        "ecosystem/defaultspack/v4/shell.fixture.default.shell.v1.json": {
            "provider_id": "shell.fixture.default",
            "availability": "verified",
            "artifact_digest": digest,
            "launch": {"variants": [{
                "artifact_id": artifact_id,
                "artifact_digest": digest,
                "artifact_ref": artifact_ref,
            }]},
        },
    }
    for relative, value in files.items():
        path = app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    presentation = app / "bundled/presentation-artifacts/fixture/fixture-shell"
    presentation.parent.mkdir(parents=True, exist_ok=True)
    presentation.write_bytes(b"presentation shell\n")
    platform = app / "ecosystem/defaultspack/platform-artifacts" / artifact_ref
    platform.parent.mkdir(parents=True, exist_ok=True)
    platform.write_bytes(b"runtime shell\n")
    for relative in (
        "app.py",
        "ecosystem/defaultspack/defaultspack/desktop_app.py",
        "core_runtime/host_broker/computer_host_helper.py",
    ):
        source = ROOT / "tobkiri_runtime" / relative
        destination = app / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    return app


def _run_reseal(sealed: Path, application: Path, target: str) -> subprocess.CompletedProcess[str]:
    digest = BUILDER._sha256_file(sealed / BUILDER.MANIFEST_FILENAME)
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(BUILDER_PATH),
            "--target",
            target,
            "--output-root",
            str(sealed),
            "--base-root",
            str(sealed),
            "--expected-base-manifest-sha256",
            digest,
            "--rebase-application-source",
            str(application),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_application_reseal_cli_replaces_stale_pre_generation_copy(tmp_path: Path) -> None:
    target = "x86_64-unknown-linux-gnu"
    sealed = FIXTURES._fixture_sources(tmp_path / "sealed", target)[2]
    sealed.parent.chmod(0o755)
    application = _packaged_application_closure(tmp_path / "outer")
    old_manifest = BUILDER._sha256_file(sealed / BUILDER.MANIFEST_FILENAME)

    result = _run_reseal(sealed, application, target)

    assert result.returncode == 0, result.stderr
    new_manifest = BUILDER._sha256_file(sealed / BUILDER.MANIFEST_FILENAME)
    assert new_manifest != old_manifest
    assert f"TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256={new_manifest}" in result.stdout
    BUILDER.validate_environment(sealed, target, run_native_smoke=False)
    BUILDER.verify_packaged_application_closure(application, sealed)


@pytest.mark.parametrize(
    "mutation",
    ("build_required", "null_digest", "empty_variants", "missing_platform_artifact"),
)
def test_application_reseal_cli_rejects_incomplete_generated_binding(
    tmp_path: Path, mutation: str
) -> None:
    target = "x86_64-unknown-linux-gnu"
    sealed = FIXTURES._fixture_sources(tmp_path / "sealed", target)[2]
    sealed.parent.chmod(0o755)
    application = _packaged_application_closure(tmp_path / "outer")
    definition_path = application / (
        "ecosystem/defaultspack/v4/shell.fixture.default.shell.v1.json"
    )
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    if mutation == "build_required":
        definition["availability"] = "build_required"
    elif mutation == "null_digest":
        definition["artifact_digest"] = None
    elif mutation == "empty_variants":
        definition["launch"]["variants"] = []
    else:
        (application / "ecosystem/defaultspack/platform-artifacts/fixture-shell").unlink()
    if mutation != "missing_platform_artifact":
        definition_path.write_text(
            json.dumps(definition, sort_keys=True) + "\n", encoding="utf-8"
        )
    old_manifest = BUILDER._sha256_file(sealed / BUILDER.MANIFEST_FILENAME)

    result = _run_reseal(sealed, application, target)

    assert result.returncode == 1
    assert BUILDER._sha256_file(sealed / BUILDER.MANIFEST_FILENAME) == old_manifest
