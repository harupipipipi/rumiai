from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFY = _load("verify_presentation_release")
PACKAGE = _load("package_presentation_artifact")


def _release(root: Path) -> tuple[Path, dict[str, object]]:
    repository_root = Path(__file__).resolve().parents[3]
    source_catalog_path = (
        repository_root
        / "tobkiri_launcher"
        / "src-tauri"
        / "bundled"
        / "presentation_catalog.json"
    )
    catalog = json.loads(source_catalog_path.read_text(encoding="utf-8"))
    variant = catalog["shell_providers"][0]["artifact_variants"][0]
    variant.update(
        {
            "artifact_id": "shell.tauri.default.linux-x86_64",
            "architecture": "x86_64",
            "bundle_identifier": None,
            "platform": "linux",
            "variant": "linux-x86_64",
        }
    )
    catalog_path = root / "presentation_catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    artifact = Path(shutil.which("true") or "/usr/bin/true")
    manifest = root / "shell_build_output.v4.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "io.tobkiri.shell.build-output.v4",
                "artifact_id": "shell.tauri.default.linux-x86_64",
                "artifact_path": os.fspath(artifact),
                "platform": "linux",
                "architecture": "x86_64",
                "build_profile": "release",
                "source_identity": "test:headless-release",
                "source_revision": "a974ec811bd189c413557a00b4b073bc5898bd41",
            }
        )
    )
    key = root / "signing-key.raw"
    key.write_bytes(bytes(range(32)))
    release = root / "Resources" / "app"
    report = PACKAGE.package_artifact(
        catalog_path, manifest, key, "headless-test-key", release
    )
    catalog_output = release / "presentation_catalog.json"
    packaged_catalog = release / "bundled" / "presentation_catalog.json"
    packaged_catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog_output.replace(packaged_catalog)
    return release, report


def test_release_scanner_verifies_signed_artifact_and_rejects_tampering() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-release-scan-") as temp:
        resource_root, report = _release(Path(temp))
        catalog_path = resource_root / "bundled" / "presentation_catalog.json"
        catalog = VERIFY.load_catalog(catalog_path)

        verified = VERIFY.verify_catalog(catalog, resource_root)
        assert report["artifact_id"] in verified["verified_artifact_ids"]
        assert verified["release"]["key_id"] == "headless-test-key"

        artifact = resource_root / str(report["path"])
        artifact.write_bytes(artifact.read_bytes() + b"tamper")
        with pytest.raises(RuntimeError, match="digest mismatch"):
            VERIFY.verify_catalog(catalog, resource_root)


def test_release_scanner_rejects_catalog_index_lock_and_signature_tampering() -> None:
    targets = (
        ("bundled/presentation_catalog.json", "signed catalog digest mismatch"),
        (
            "bundled/shell_artifact_index.v4.json",
            "signed artifact index digest mismatch",
        ),
        ("bundled/shell_profile_lock.v4.json", "signed profile lock digest mismatch"),
        ("bundled/presentation_release.v4.json", "signature verification failed"),
    )
    for relative, message in targets:
        with TemporaryDirectory(
            prefix="tobkiri-presentation-binding-negative-"
        ) as temp:
            resource_root, _ = _release(Path(temp))
            catalog_path = resource_root / "bundled" / "presentation_catalog.json"
            catalog = VERIFY.load_catalog(catalog_path)
            target = resource_root / relative
            if relative.endswith("presentation_release.v4.json"):
                value = json.loads(target.read_text())
                value["signature"] = "A" * len(value["signature"])
                target.write_text(json.dumps(value))
            else:
                target.write_bytes(target.read_bytes() + b" ")
            with pytest.raises(RuntimeError, match=message):
                VERIFY.verify_catalog(catalog, resource_root)
