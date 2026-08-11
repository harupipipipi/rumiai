from __future__ import annotations

import base64
import importlib.util
import json
import os
import plistlib
import shutil
import subprocess
import sys
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


def _windows_catalog(entrypoint: str = "tobkiri-shell.exe") -> dict[str, object]:
    """Return the production Windows variant used by path portability tests."""
    catalog = _catalog(entrypoint)
    variant = catalog["shell_providers"][0]["artifact_variants"][0]
    variant.update(
        artifact_id="shell.cli.default.windows-x86_64",
        variant="windows-x86_64",
        platform="windows",
    )
    return catalog


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


def test_windows_absolute_artifact_path_accepts_canonical_contained_path() -> None:
    value = (
        r"D:\a\tobkiri\tobkiri\tobkiri_launcher\src-tauri\target"
        r"\x86_64-pc-windows-msvc\release\tobkiri-shell.exe"
    )
    result = MODULE._canonical_windows_absolute_artifact_path(
        value, r"d:\A\TOBKIRI\TOBKIRI"
    )
    assert str(result) == value


@pytest.mark.parametrize(
    "value",
    [
        r"E:\a\tobkiri\tobkiri\tobkiri-shell.exe",
        r"C:tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\..\outside\tobkiri-shell.exe",
        r"\\server\share\tobkiri\tobkiri-shell.exe",
        r"\\?\D:\a\tobkiri\tobkiri\tobkiri-shell.exe",
        r"\\.\D:\a\tobkiri\tobkiri\tobkiri-shell.exe",
        r"D:/a/tobkiri/tobkiri/tobkiri-shell.exe",
        r"D:\a/tobkiri\tobkiri\tobkiri-shell.exe",
        r"D:\a\\tobkiri\tobkiri\tobkiri-shell.exe",
        r"D:\a\.\tobkiri\tobkiri\tobkiri-shell.exe",
        "D:\\a\\tobkiri\\tobkiri\\tobkiri-shell.exe\x00ignored",
        r"D:\a\tobkiri\outside\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\release.\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\CON\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\CONIN$\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\CONOUT$.txt\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\COM¹\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\COM².txt\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\COM³\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\LPT¹\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\LPT².txt\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\LPT³\tobkiri-shell.exe",
        r"D:\a\tobkiri\tobkiri\tobkiri-shell.exe:payload",
    ],
)
def test_windows_absolute_artifact_path_rejects_noncanonical_or_escape(
    value: str,
) -> None:
    with pytest.raises(RuntimeError, match="release artifact path"):
        MODULE._canonical_windows_absolute_artifact_path(
            value, r"D:\a\tobkiri\tobkiri"
        )


def test_windows_absolute_artifact_path_requires_windows_and_repository_root() -> None:
    with TemporaryDirectory(prefix="tobkiri-windows-path-gate-") as temp:
        root = Path(temp)
        catalog, manifest, key = _fixture(root)
        build = json.loads(manifest.read_text())
        build.update(
            artifact_id="shell.cli.default.windows-x86_64",
            artifact_path=r"D:\a\tobkiri\tobkiri\tobkiri-shell.exe",
            platform="windows",
        )
        catalog.write_text(json.dumps(_windows_catalog()), encoding="utf-8")
        manifest.write_text(json.dumps(build), encoding="utf-8")
        with pytest.raises(RuntimeError, match="release artifact path is unsafe"):
            package_artifact(catalog, manifest, key, "key", root / "release")

        build.update(
            artifact_id="shell.cli.default.linux-x86_64",
            platform="linux",
        )
        catalog.write_text(json.dumps(_catalog()), encoding="utf-8")
        manifest.write_text(json.dumps(build), encoding="utf-8")
        with pytest.raises(RuntimeError, match="release artifact path is unsafe"):
            package_artifact(catalog, manifest, key, "key", root / "linux-release")


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows Path semantics")
def test_windows_absolute_artifact_path_packages_native_manifest() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    ignored_target = repository_root / "tobkiri_launcher/src-tauri/target"
    ignored_target.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="tobkiri-windows-path-", dir=ignored_target
    ) as source_temp, TemporaryDirectory(
        prefix="tobkiri-windows-output-"
    ) as output_temp:
        source = Path(source_temp) / "tobkiri-shell.exe"
        source.write_bytes(b"MZ-stub-windows\r\n")
        source.chmod(0o755)

        root = Path(output_temp)
        catalog = root / "presentation_catalog.json"
        catalog.write_text(json.dumps(_windows_catalog()), encoding="utf-8")
        manifest = root / "shell_build_output.v4.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": "io.tobkiri.shell.build-output.v4",
                    "artifact_id": "shell.cli.default.windows-x86_64",
                    "artifact_path": os.fspath(source.resolve()),
                    "platform": "windows",
                    "architecture": "x86_64",
                    "build_profile": "release",
                    "source_identity": MODULE.source_identity_for_repository(
                        repository_root
                    ),
                    "source_revision": MODULE.source_revision_for_repository(
                        repository_root
                    ),
                }
            ),
            encoding="utf-8",
        )
        key = root / "signing-key.raw"
        key.write_bytes(bytes(range(32)))

        report = package_artifact(
            catalog,
            manifest,
            key,
            "windows-path-test-key",
            root / "release",
            repository_root,
        )
        assert "\\" not in str(report["path"])
        index = json.loads(
            (root / "release/bundled/shell_artifact_index.v4.json").read_text(
                encoding="utf-8"
            )
        )
        assert index["path"] == report["path"]
        assert "\\" not in index["path"]


def _package(root: Path) -> dict[str, object]:
    catalog, manifest, key = _fixture(root)
    return package_artifact(
        catalog, manifest, key, "test-release-key", root / "release"
    )


def _macos_fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    """Create the smallest real macOS application fixture accepted by codesign."""
    app = root / "Tobkiri.app"
    executable = app / "Contents" / "MacOS" / "tobkiri-shell"
    executable.parent.mkdir(parents=True)
    shutil.copyfile("/usr/bin/true", executable)
    executable.chmod(0o755)
    resources = app / "Contents" / "Resources"
    resources.mkdir()
    (resources / "presentation.json").write_text("sealed fixture\n", encoding="utf-8")
    with (app / "Contents" / "Info.plist").open("wb") as handle:
        plistlib.dump(
            {
                "CFBundleExecutable": "tobkiri-shell",
                "CFBundleIdentifier": "io.tobkiri.shell.tauri",
                "CFBundlePackageType": "APPL",
            },
            handle,
        )
    catalog = _catalog("Tobkiri.app/Contents/MacOS/tobkiri-shell")
    variant = catalog["shell_providers"][0]["artifact_variants"][0]
    variant.update(
        artifact_id="shell.cli.default.macos-arm64",
        platform="macos",
        architecture="arm64",
        bundle_identifier="io.tobkiri.shell.tauri",
    )
    catalog_path = root / "presentation_catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    manifest = root / "shell_build_output.v4.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "io.tobkiri.shell.build-output.v4",
                "artifact_id": "shell.cli.default.macos-arm64",
                "artifact_path": os.fspath(app),
                "platform": "macos",
                "architecture": "arm64",
                "build_profile": "release",
                "source_identity": "github:example/tobkiri",
                "source_revision": "a974ec811bd189c413557a00b4b073bc5898bd41",
            }
        ),
        encoding="utf-8",
    )
    key = root / "signing-key.raw"
    key.write_bytes(bytes(range(32)))
    return catalog_path, manifest, key, app


def _codesign_app(app: Path) -> None:
    subprocess.run(
        ["/usr/bin/codesign", "--force", "--sign", "-", os.fspath(app)],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS codesign")
def test_package_preserves_valid_macos_resource_envelope() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-macos-valid-") as temp:
        root = Path(temp)
        catalog, manifest, key, app = _macos_fixture(root)
        _codesign_app(app)
        report = package_artifact(
            catalog, manifest, key, "key", root / "release"
        )
        staged = root / "release" / str(report["path"])
        assert (staged / "Contents/_CodeSignature/CodeResources").is_file()
        subprocess.run(
            [
                "/usr/bin/codesign",
                "--verify",
                "--deep",
                "--strict",
                os.fspath(staged),
            ],
            check=True,
        )


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS codesign")
@pytest.mark.parametrize("tamper", ["missing-code-resources", "resource-mismatch"])
def test_package_rejects_invalid_macos_resource_envelope(tamper: str) -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-macos-invalid-") as temp:
        root = Path(temp)
        catalog, manifest, key, app = _macos_fixture(root)
        _codesign_app(app)
        if tamper == "missing-code-resources":
            (app / "Contents/_CodeSignature/CodeResources").unlink()
        else:
            (app / "Contents/Resources/presentation.json").write_text(
                "tampered fixture\n", encoding="utf-8"
            )
        with pytest.raises(RuntimeError, match="signature verification failed"):
            package_artifact(catalog, manifest, key, "key", root / "release")
        assert not (root / "release").exists()


def test_desktop_installer_signs_macos_shell_after_build_before_packaging() -> None:
    workflow = (
        Path(__file__).resolve().parents[3]
        / ".github/workflows/desktop-installers.yml"
    ).read_text(encoding="utf-8")
    build = workflow.index("- name: Build verified Tauri Shell artifact")
    sign = workflow.index("- name: Ad-hoc sign macOS Tauri Shell artifact")
    stage = workflow.index("- name: Stage verified macOS Tauri Shell artifact")
    assert build < sign < stage
    signing_step = workflow[sign:stage]
    assert "/usr/bin/codesign --force --sign - \"$artifact\"" in signing_step
    assert (
        "/usr/bin/codesign --verify --deep --strict --verbose=2 \"$artifact\""
        in signing_step
    )


def test_package_binds_exact_build_output_to_signed_index_and_lock() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-package-test-") as temp:
        root = Path(temp)
        report = _package(root)
        output = root / "release"
        staged = output / str(report["path"])
        assert staged.is_file() and os.access(staged, os.X_OK)
        assert report["sha256"] == artifact_digest(staged)
        assert report["entrypoint_sha256"] == MODULE.file_digest(staged)
        assert report["size"] == staged.stat().st_size
        subprocess.run([staged], check=True)

        catalog = json.loads((output / "presentation_catalog.json").read_text())
        variant = catalog["shell_providers"][0]["artifact_variants"][0]
        assert variant["path"] == report["path"]
        assert variant["sha256"] == report["sha256"]
        assert variant["entrypoint_sha256"] == report["entrypoint_sha256"]
        assert variant["source_revision"] == report["source_revision"]
        index = json.loads(
            (output / "bundled/shell_artifact_index.v4.json").read_text()
        )
        lock = json.loads((output / "bundled/shell_profile_lock.v4.json").read_text())
        assert index["artifact_id"] == lock["artifact_id"] == report["artifact_id"]
        assert lock["artifact_sha256"] == report["sha256"]
        assert (
            index["entrypoint_sha256"]
            == lock["entrypoint_sha256"]
            == report["entrypoint_sha256"]
        )

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

        build["source_revision"] = "a" * 40
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


def test_package_rejects_dirty_release_checkout() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-source-dirty-") as temp:
        root = Path(temp)
        repository_root = root / "source"
        repository_root.mkdir()
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=repository_root,
            check=True,
        )
        marker = repository_root / "tracked.txt"
        marker.write_text("clean\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repository_root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Tobkiri Test",
                "-c",
                "user.email=test@invalid",
                "commit",
                "--quiet",
                "-m",
                "fixture",
            ],
            cwd=repository_root,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://github.com/example/tobkiri.git",
            ],
            cwd=repository_root,
            check=True,
        )
        fixture_root = root / "fixture"
        fixture_root.mkdir()
        catalog, manifest, key = _fixture(fixture_root)
        build = json.loads(manifest.read_text())
        build["source_identity"] = MODULE.source_identity_for_repository(
            repository_root
        )
        build["source_revision"] = MODULE.source_revision_for_repository(
            repository_root
        )
        manifest.write_text(json.dumps(build))

        marker.write_text("dirty\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="dirty source checkout"):
            package_artifact(
                catalog,
                manifest,
                key,
                "key",
                root / "dirty-output",
                repository_root,
            )
        assert not (root / "dirty-output").exists()


def test_package_accepts_isolated_panel_regeneration_but_rejects_unrelated_dirt() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-isolated-panel-") as temp:
        root = Path(temp)
        repository_root = root / "source"
        panel = repository_root / (
            "tobkiri_runtime/core_runtime/core_pack/core_control_panel/web"
        )
        panel.mkdir(parents=True)
        marker = repository_root / "unrelated.txt"
        marker.write_text("clean\n", encoding="utf-8")
        (panel / "index.html").write_text("checked-in\n", encoding="utf-8")
        subprocess.run(["git", "init", "--quiet"], cwd=repository_root, check=True)
        subprocess.run(["git", "add", "."], cwd=repository_root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Tobkiri Test",
                "-c",
                "user.email=test@invalid",
                "commit",
                "--quiet",
                "-m",
                "fixture",
            ],
            cwd=repository_root,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://github.com/example/tobkiri.git",
            ],
            cwd=repository_root,
            check=True,
        )

        fixture_root = root / "fixture"
        fixture_root.mkdir()
        catalog, manifest, key = _fixture(fixture_root)
        build = json.loads(manifest.read_text())
        build["source_identity"] = MODULE.source_identity_for_repository(
            repository_root
        )
        build["source_revision"] = MODULE.source_revision_for_repository(
            repository_root
        )
        manifest.write_text(json.dumps(build), encoding="utf-8")

        isolated_panel = root / "runner-temp" / "tobkiri-panel-build"
        isolated_panel.mkdir(parents=True)
        (isolated_panel / "index.html").write_text("regenerated\n", encoding="utf-8")
        package_artifact(
            catalog,
            manifest,
            key,
            "key",
            root / "isolated-output",
            repository_root,
        )
        assert (
            (panel / "index.html").read_text(encoding="utf-8") == "checked-in\n"
        )
        assert (
            (isolated_panel / "index.html").read_text(encoding="utf-8")
            == "regenerated\n"
        )

        marker.write_text("tampered\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="dirty source checkout"):
            package_artifact(
                catalog,
                manifest,
                key,
                "key",
                root / "tampered-output",
                repository_root,
            )
        assert not (root / "tampered-output").exists()


def _file_bytes(root: Path) -> dict[str, bytes]:
    """Return a deterministic byte snapshot for transaction assertions."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _linux_source(path: Path, payload: bytes = b"old-source") -> Path:
    """Create a small recognized x86_64 ELF fixture."""
    path.write_bytes(
        b"\x7fELF\x02\x01\x01\x00"
        + b"\x00" * 10
        + b">\x00"
        + payload
    )
    path.chmod(0o755)
    return path


def test_package_normalizes_entrypoint_and_rolls_back_write_fault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-atomic-escape-") as temp:
        root = Path(temp)
        catalog, manifest, key = _fixture(root)
        unsafe = json.loads(catalog.read_text())
        unsafe["shell_providers"][0]["artifact_variants"][0]["entrypoint"] = (
            "../true"
        )
        catalog.write_text(json.dumps(unsafe))
        outside = root / "outside"
        outside.write_bytes(b"sentinel")
        with pytest.raises(RuntimeError, match="entrypoint is unsafe"):
            package_artifact(catalog, manifest, key, "key", root / "escape-output")
        assert outside.read_bytes() == b"sentinel"
        assert not (root / "escape-output").exists()

        catalog.write_text(json.dumps(_catalog()))
        original = MODULE._write_json
        calls = 0

        def fail_on_second(path: Path, value: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected pack write fault")
            original(path, value)

        output = root / "existing-output"
        output.mkdir()
        (output / "sentinel").write_bytes(b"keep-existing-bytes")
        before = _file_bytes(output)
        monkeypatch.setattr(MODULE, "_write_json", fail_on_second)
        with pytest.raises(OSError, match="injected pack write fault"):
            package_artifact(catalog, manifest, key, "key", output)
        assert _file_bytes(output) == before
        assert not list(root.glob(".tobkiri-presentation-stage-*"))


def test_package_uses_one_source_snapshot_and_revalidates_staged_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-snapshot-") as temp:
        root = Path(temp)
        source = _linux_source(root / "source-shell")
        catalog, manifest, key = _fixture(root, artifact_path=os.fspath(source))
        original_snapshot = MODULE._snapshot_artifact

        def replace_after_snapshot(source_path: Path, destination: Path) -> Path:
            result = original_snapshot(source_path, destination)
            _linux_source(source_path, b"replaced-after-snapshot")
            return result

        monkeypatch.setattr(MODULE, "_snapshot_artifact", replace_after_snapshot)
        report = package_artifact(catalog, manifest, key, "key", root / "release")
        staged = root / "release" / str(report["path"])
        assert staged.read_bytes() == source.read_bytes().replace(
            b"replaced-after-snapshot", b"old-source"
        )

        calls: list[Path] = []
        monkeypatch.setattr(
            MODULE,
            "_validate_macos_signature",
            lambda artifact, platform: calls.append(artifact),
        )
        second = root / "release-second"
        package_artifact(catalog, manifest, key, "key", second)
        assert len(calls) == 2
        assert all("source-snapshot" not in path.parts for path in calls)
        assert all(path.is_relative_to(second.parent) for path in calls)


def test_package_two_passes_are_byte_identical() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-deterministic-") as temp:
        root = Path(temp)
        catalog, manifest, key = _fixture(root)
        first = root / "release-one"
        second = root / "release-two"
        package_artifact(catalog, manifest, key, "key", first)
        package_artifact(catalog, manifest, key, "key", second)
        assert _file_bytes(first) == _file_bytes(second)


def test_package_rejects_absolute_entrypoint_before_creating_output() -> None:
    with TemporaryDirectory(prefix="tobkiri-presentation-absolute-") as temp:
        root = Path(temp)
        catalog, manifest, key = _fixture(root)
        value = json.loads(catalog.read_text())
        value["shell_providers"][0]["artifact_variants"][0]["entrypoint"] = os.fspath(
            Path("/tmp/outside-shell")
        )
        catalog.write_text(json.dumps(value))
        with pytest.raises(RuntimeError, match="entrypoint is unsafe"):
            package_artifact(catalog, manifest, key, "key", root / "release")
        assert not (root / "release").exists()
