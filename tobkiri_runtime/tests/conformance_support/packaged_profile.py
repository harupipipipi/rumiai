"""Faithful packaged Profile bundle fixtures for conformance tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from ecosystem.defaultspack.domain.runtime_v4 import BundledCatalog
from scripts.generate_packaged_defaultspack_v4_bundle import stage_packaged_bundle
from tobkiri_protocol.platform_artifact import verify_platform_artifact


_INJECTED_BUNDLE_ROOT: Path | None = None


def inject_packaged_profile_bundle(root: Path | None) -> None:
    """Install the session fixture dependency for test code only."""

    global _INJECTED_BUNDLE_ROOT
    _INJECTED_BUNDLE_ROOT = root


def packaged_profile_bundle_root() -> Path:
    """Return the explicitly injected packaged fixture root."""

    if _INJECTED_BUNDLE_ROOT is None:
        raise RuntimeError("packaged Profile test dependency was not injected")
    return _INJECTED_BUNDLE_ROOT


def load_packaged_profile_catalog() -> BundledCatalog:
    """Load the session's canonical packaged Profile fixture."""

    return BundledCatalog.load(packaged_profile_bundle_root())


def build_packaged_profile_bundle(
    source_bundle: Path,
    destination: Path,
    *,
    source_commit: str,
    source_tree: str,
    source_clean: bool,
    source_snapshot_root: Path,
) -> Path:
    """Build a verified Linux/x86_64 Profile bundle around fixture bytes.

    The generator is intentionally a preverified-snapshot consumer.  Keep the
    provenance arguments explicit here so conformance fixtures exercise the
    same boundary as release packaging and cannot silently rediscover Git.
    """

    bundle = destination / "defaultspack" / "v4"
    artifacts = destination / "defaultspack" / "platform-artifacts"
    executable = destination / "verified-release" / "Tobkiri.AppImage"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 10 + b">\x00fixture")
    executable.chmod(0o755)
    shutil.copytree(source_bundle, bundle)
    stage_packaged_bundle(
        source_artifact=executable,
        bundle_root=bundle,
        artifact_root=artifacts,
        relative_path="Tobkiri.AppImage",
        entrypoint="Tobkiri.AppImage",
        platform="linux",
        architecture="x86_64",
        bundle_identity="io.tobkiri.shell.tauri",
        source_commit=source_commit,
        source_tree=source_tree,
        source_clean=source_clean,
        source_snapshot_root=source_snapshot_root,
    )
    catalog = BundledCatalog.load(bundle)
    shell = catalog.shells["shell.tauri.default"]
    variants = shell["launch"]["variants"]
    if len(variants) != 1 or catalog.artifact_root is None:
        raise AssertionError("packaged Profile fixture has no exact Shell artifact")
    verify_platform_artifact(catalog.artifact_root, variants[0])
    return bundle


__all__ = [
    "build_packaged_profile_bundle",
    "inject_packaged_profile_bundle",
    "load_packaged_profile_catalog",
    "packaged_profile_bundle_root",
]
