"""Faithful packaged Profile bundle fixtures for conformance tests."""

from __future__ import annotations

import plistlib
import shutil
from pathlib import Path

from scripts.generate_packaged_defaultspack_v4_bundle import package_bundle


def build_packaged_profile_bundle(
    source_bundle: Path,
    destination: Path,
    *,
    source_commit: str,
) -> Path:
    """Build a verified macOS/arm64 Profile bundle around fixture bytes."""

    bundle = destination / "defaultspack" / "v4"
    artifacts = destination / "defaultspack" / "platform-artifacts"
    application = artifacts / "Tobkiri.app"
    executable = application / "Contents" / "MacOS" / "tobkiri"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"\xcf\xfa\xed\xfe\x0c\x00\x00\x01fixture")
    executable.chmod(0o755)
    (application / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleIdentifier": "io.tobkiri.shell.tauri"})
    )
    shutil.copytree(source_bundle, bundle)
    package_bundle(
        bundle_root=bundle,
        artifact_root=artifacts,
        relative_path="Tobkiri.app",
        entrypoint="Tobkiri.app/Contents/MacOS/tobkiri",
        platform="macos",
        architecture="arm64",
        bundle_identity="io.tobkiri.shell.tauri",
        source_commit=source_commit,
    )
    return bundle


__all__ = ["build_packaged_profile_bundle"]
