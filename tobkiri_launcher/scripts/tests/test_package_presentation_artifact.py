from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "package_presentation_artifact.py"
SPEC = importlib.util.spec_from_file_location(
    "package_presentation_artifact", SCRIPT_PATH
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
artifact_digest = MODULE.artifact_digest
package_artifact = MODULE.package_artifact


def _catalog(entrypoint: str = "true") -> dict[str, object]:
    return {
        "schema": "io.tobkiri.launcher.presentation-catalog.v1",
        "default_selection": {
            "base_pack_id": "defaults-basepack",
            "shell_provider_id": "shell.cli.default",
        },
        "shell_providers": [
            {
                "provider_id": "shell.cli.default",
                "artifact_variants": [
                    {
                        "artifact_id": "shell.cli.default.linux-x86_64",
                        "variant": "linux-x86_64",
                        "platform": "linux",
                        "architecture": "x86_64",
                        "entrypoint": entrypoint,
                        "prebuilt": True,
                        "production": True,
                        "development_command": None,
                    }
                ],
            }
        ],
    }


def _fixture(
    root: Path, *, artifact_path: str | None = None
) -> tuple[Path, Path, Path]:
    catalog_path = root / "presentation_catalog.json"
    catalog_path.write_text(json.dumps(_catalog()), encoding="utf-8")
    source = Path(shutil.which("true") or "/usr/bin/true")
    manifest = root / "shell_build_output.v4.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "io.tobkiri.shell.build-output.v4",
                "artifact_id": "shell.cli.default.linux-x86_64",
                "artifact_path": artifact_path or os.fspath(source),
                "platform": "linux",
                "architecture": "x86_64",
                "build_profile": "release",
                "source_identity": "github:example/tobkiri",
                "source_revision": "a974ec811bd189c413557a00b4b073bc5898bd41",
            }
        ),
        encoding="utf-8",
    )
    key = root / "signing-key.raw"
    key.write_bytes(bytes(range(32)))
    return catalog_path, manifest, key


def _package(root: Path) -> dict[str, object]:
    catalog, manifest, key = _fixture(root)
    return package_artifact(
        catalog, manifest, key, "test-release-key", root / "release"
    )


def test_package_binds_exact_build_output_to_signed_index_and_lock() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-package-test-") as temp:
        root = Path(temp)
        report = _package(root)
        output = root / "release"
        staged = output / str(report["path"])
        assert staged.is_file() and os.access(staged, os.X_OK)
        assert report["sha256"] == artifact_digest(staged)
        assert report["size"] == staged.stat().st_size
        subprocess.run([staged], check=True)

        catalog = json.loads((output / "presentation_catalog.json").read_text())
        variant = catalog["shell_providers"][0]["artifact_variants"][0]
        assert variant["path"] == report["path"]
        assert variant["sha256"] == report["sha256"]
        assert variant["source_revision"] == report["source_revision"]
        index = json.loads(
            (output / "bundled/shell_artifact_index.v4.json").read_text()
        )
        lock = json.loads((output / "bundled/shell_profile_lock.v4.json").read_text())
        assert index["artifact_id"] == lock["artifact_id"] == report["artifact_id"]
        assert lock["artifact_sha256"] == report["sha256"]

        release = json.loads(
            (output / "bundled/presentation_release.v4.json").read_text()
        )
        message = MODULE._signature_message(release)
        Ed25519PublicKey.from_public_bytes(
            base64.b64decode(release["public_key"])
        ).verify(base64.b64decode(release["signature"]), message)


def test_package_rejects_missing_symlink_wrong_platform_and_dev_metadata() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-package-negative-") as temp:
        root = Path(temp)
        catalog, manifest, key = _fixture(root, artifact_path="missing")
        with pytest.raises(RuntimeError, match="missing or symlinked"):
            package_artifact(catalog, manifest, key, "key", root / "missing-output")

        source = Path(shutil.which("true") or "/usr/bin/true")
        symlink = root / "symlink"
        symlink.symlink_to(source)
        build = json.loads(manifest.read_text())
        build["artifact_path"] = os.fspath(symlink)
        manifest.write_text(json.dumps(build))
        with pytest.raises(RuntimeError, match="missing or symlinked"):
            package_artifact(catalog, manifest, key, "key", root / "symlink-output")

        build["artifact_path"] = os.fspath(source)
        build["platform"] = "macos"
        manifest.write_text(json.dumps(build))
        with pytest.raises(RuntimeError, match="platform/architecture"):
            package_artifact(catalog, manifest, key, "key", root / "platform-output")

        build["platform"] = "linux"
        build["architecture"] = "arm64"
        manifest.write_text(json.dumps(build))
        with pytest.raises(RuntimeError, match="unsupported platform/architecture"):
            package_artifact(catalog, manifest, key, "key", root / "architecture-output")

        untrusted = _catalog()
        untrusted["shell_providers"][0]["artifact_variants"][0][
            "development_command"
        ] = "cargo tauri dev"
        catalog.write_text(json.dumps(untrusted))
        build["platform"] = "linux"
        manifest.write_text(json.dumps(build))
        with pytest.raises(RuntimeError, match="development command"):
            package_artifact(catalog, manifest, key, "key", root / "dev-output")


def test_package_rejects_empty_source_identity_and_bad_key() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-source-negative-") as temp:
        root = Path(temp)
        catalog, manifest, key = _fixture(root)
        build = json.loads(manifest.read_text())
        build["source_revision"] = ""
        manifest.write_text(json.dumps(build))
        with pytest.raises(RuntimeError, match="source_revision"):
            package_artifact(catalog, manifest, key, "key", root / "source-output")

        build["source_revision"] = "revision"
        manifest.write_text(json.dumps(build))
        key.write_bytes(b"short")
        with pytest.raises(RuntimeError, match="32 raw seed bytes"):
            package_artifact(catalog, manifest, key, "key", root / "key-output")


def test_package_rejects_unknown_stale_profile_and_wrong_bundle_identity() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-identity-negative-") as temp:
        root = Path(temp)
        catalog, manifest, key = _fixture(root)
        build = json.loads(manifest.read_text())

        build["artifact_id"] = "shell.unknown.linux-x86_64"
        manifest.write_text(json.dumps(build))
        with pytest.raises(RuntimeError, match="not declared"):
            package_artifact(catalog, manifest, key, "key", root / "unknown-output")

        build["artifact_id"] = "shell.cli.default.linux-x86_64"
        manifest.write_text(json.dumps(build))
        stale = json.loads(catalog.read_text())
        stale["default_selection"]["shell_provider_id"] = "shell.other.default"
        catalog.write_text(json.dumps(stale))
        with pytest.raises(RuntimeError, match="default Profile Shell"):
            package_artifact(catalog, manifest, key, "key", root / "stale-output")

        app = root / "Tobkiri.app"
        executable = app / "Contents" / "MacOS" / "tobkiri-shell"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
        plist = app / "Contents" / "Info.plist"
        plist.write_bytes(
            b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b'<plist version="1.0"><dict><key>CFBundleIdentifier</key>'
            b'<string>io.tobkiri.shell.wrong</string></dict></plist>\n'
        )
        mac_catalog = _catalog("Tobkiri.app/Contents/MacOS/tobkiri-shell")
        variant = mac_catalog["shell_providers"][0]["artifact_variants"][0]
        variant.update(
            artifact_id="shell.cli.default.macos-arm64",
            platform="macos",
            architecture="arm64",
            bundle_identifier="io.tobkiri.shell.cli.default",
        )
        catalog.write_text(json.dumps(mac_catalog))
        build.update(
            artifact_id="shell.cli.default.macos-arm64",
            artifact_path=os.fspath(app),
            platform="macos",
            architecture="arm64",
        )
        manifest.write_text(json.dumps(build))
        with pytest.raises(RuntimeError, match="bundle identity does not match"):
            package_artifact(catalog, manifest, key, "key", root / "bundle-output")

        variant["bundle_identifier"] = None
        catalog.write_text(json.dumps(mac_catalog))
        with pytest.raises(RuntimeError, match="no declared bundle identity"):
            package_artifact(catalog, manifest, key, "key", root / "missing-bundle-output")


def test_package_rejects_stale_catalog_and_artifact_path_escape() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-package-path-negative-") as temp:
        root = Path(temp)
        catalog, manifest, key = _fixture(root)
        stale = json.loads(catalog.read_text())
        stale["shell_providers"][0]["artifact_variants"][0]["path"] = (
            "bundled/presentation-artifacts/old/true"
        )
        catalog.write_text(json.dumps(stale))
        with pytest.raises(RuntimeError, match="stale installed metadata"):
            package_artifact(catalog, manifest, key, "key", root / "stale-output")

        catalog.write_text(json.dumps(_catalog()))
        build = json.loads(manifest.read_text())
        build["artifact_path"] = "../outside/true"
        manifest.write_text(json.dumps(build))
        with pytest.raises(RuntimeError, match="escapes its manifest"):
            package_artifact(catalog, manifest, key, "key", root / "escape-output")


def test_package_rejects_source_revision_from_another_checkout() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    with TemporaryDirectory(prefix="tobkiri-presentation-source-stale-") as temp:
        root = Path(temp)
        catalog, manifest, key = _fixture(root)
        build = json.loads(manifest.read_text())
        build["source_identity"] = MODULE.source_identity_for_repository(repository_root)
        build["source_revision"] = MODULE.source_revision_for_repository(repository_root)
        manifest.write_text(json.dumps(build))
        package_artifact(
            catalog,
            manifest,
            key,
            "key",
            root / "current-output",
            repository_root,
        )

        build["source_revision"] = "0" * 40
        manifest.write_text(json.dumps(build))
        with pytest.raises(RuntimeError, match="source revision is stale"):
            package_artifact(
                catalog,
                manifest,
                key,
                "key",
                root / "stale-output",
                repository_root,
            )
