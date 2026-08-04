#!/usr/bin/env python3
"""Package one verified prebuilt Shell artifact into a Launcher release.

The checked-in presentation catalog describes available variants but never
claims that an executable is installed.  Release builds call this script with
the already-built Shell bundle/binary.  The script verifies the declared
variant, copies the immutable artifact into a release staging directory, and
pins the staged path and content digest in a release-only catalog.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

CATALOG_SCHEMA = "io.tobkiri.launcher.presentation-catalog.v1"
ARTIFACT_ROOT = Path("bundled/presentation-artifacts")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse release artifact packaging arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def _reject_symlinks(path: Path) -> None:
    """Reject symlinked release inputs and descendants."""
    if path.is_symlink():
        raise RuntimeError(f"release artifact may not be a symlink: {path}")
    if not path.is_dir():
        return
    for child in path.iterdir():
        _reject_symlinks(child)


def _hash_path(path: Path, relative: Path = Path("")) -> Any:
    """Return the Launcher-compatible streaming hash for a file/tree."""
    digest = hashlib.sha256()
    _hash_path_into(path, relative, digest)
    return digest


def _hash_path_into(path: Path, relative: Path, digest: Any) -> None:
    """Hash one path using relative names and NUL separators."""
    if path.is_symlink():
        raise RuntimeError(f"release artifact may not contain a symlink: {path}")
    if path.is_file():
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(chunk)
        return
    if not path.is_dir():
        raise RuntimeError(f"release artifact is not a file or directory: {path}")
    for child in sorted(path.iterdir(), key=lambda item: item.name):
        _hash_path_into(child, relative / child.name, digest)


def artifact_digest(path: Path) -> str:
    """Return the digest format consumed by the Rust Launcher resolver."""
    return "sha256:" + _hash_path(path).hexdigest()


def _load_catalog(path: Path) -> dict[str, Any]:
    """Load a checked-in presentation catalog."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"failed to read presentation catalog {path}: {error}"
        ) from error
    if not isinstance(value, dict) or value.get("schema") != CATALOG_SCHEMA:
        raise RuntimeError(f"unsupported presentation catalog: {path}")
    return value


def _find_variant(catalog: Mapping[str, Any], artifact_id: str) -> dict[str, Any]:
    """Return the exact declared variant or fail closed."""
    for shell in catalog.get("shell_providers", []):
        if not isinstance(shell, Mapping):
            continue
        for variant in shell.get("artifact_variants", []):
            if isinstance(variant, dict) and variant.get("artifact_id") == artifact_id:
                return variant
    raise RuntimeError(
        f"artifact variant is not declared in the catalog: {artifact_id}"
    )


def _validate_bundle_identity(artifact: Path, expected: str | None) -> None:
    """Validate a macOS bundle identity when the descriptor pins one."""
    if not expected or artifact.suffix != ".app":
        return
    plist_path = artifact / "Contents" / "Info.plist"
    if not plist_path.is_file():
        raise RuntimeError(f"macOS artifact is missing Info.plist: {artifact}")
    try:
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as error:
        raise RuntimeError(
            f"macOS artifact Info.plist is invalid: {plist_path}"
        ) from error
    if plist.get("CFBundleIdentifier") != expected:
        raise RuntimeError(
            "macOS artifact bundle identity does not match the catalog: "
            f"expected {expected!r}, got {plist.get('CFBundleIdentifier')!r}"
        )


def _validate_macos_signature(artifact: Path, platform: str) -> None:
    """Require strict code-signature verification for macOS bundles."""
    if platform != "macos":
        return
    codesign = Path("/usr/bin/codesign")
    if not codesign.is_file():
        raise RuntimeError("macOS release packaging requires /usr/bin/codesign")
    result = subprocess.run(
        [os.fspath(codesign), "--verify", "--deep", "--strict", os.fspath(artifact)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"macOS artifact signature verification failed: {detail}")


def _validate_entrypoint(artifact: Path, entrypoint: str) -> None:
    """Ensure the declared executable exists and is executable."""
    entry = Path(entrypoint)
    if entry.is_absolute() or ".." in entry.parts:
        raise RuntimeError(f"artifact entrypoint is unsafe: {entrypoint}")

    if artifact.is_dir():
        top = entry.parts[0] if entry.parts else ""
        candidate = (
            artifact / Path(*entry.parts[1:])
            if top == artifact.name
            else artifact / entry
        )
    else:
        candidate = artifact
    if not candidate.is_file():
        raise RuntimeError(f"declared artifact entrypoint is missing: {candidate}")
    if not (candidate.stat().st_mode & stat.S_IXUSR):
        raise RuntimeError(
            f"declared artifact entrypoint is not executable: {candidate}"
        )


def _copy_artifact(source: Path, destination_dir: Path, entrypoint: str) -> Path:
    """Copy an artifact under a deterministic, bundle-local name."""
    destination_dir.mkdir(parents=True, exist_ok=False)
    if source.is_dir():
        name = Path(entrypoint).parts[0]
        destination = destination_dir / name
        _copy_tree(source, destination)
    else:
        destination = destination_dir / Path(entrypoint).name
        _copy_file(source, destination)
    _reject_symlinks(destination)
    return destination


def _copy_file(source: Path, destination: Path) -> None:
    """Copy bytes and executable mode without copying platform flags/owners."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(stat.S_IMODE(source.stat().st_mode))


def _copy_tree(source: Path, destination: Path) -> None:
    """Copy a tree without following or reproducing symlinks."""
    destination.mkdir(parents=True, exist_ok=False)
    destination.chmod(stat.S_IMODE(source.stat().st_mode))
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        target = destination / child.name
        if child.is_symlink():
            raise RuntimeError(f"release artifact may not contain a symlink: {child}")
        if child.is_dir():
            _copy_tree(child, target)
        elif child.is_file():
            _copy_file(child, target)
        else:
            raise RuntimeError(f"unsupported release artifact entry: {child}")


def package_artifact(
    catalog_path: Path,
    artifact_id: str,
    artifact_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Verify and stage one prebuilt artifact for a release build."""
    catalog = _load_catalog(catalog_path.resolve())
    variant = _find_variant(catalog, artifact_id)
    if variant.get("prebuilt") is not True or variant.get("production") is not True:
        raise RuntimeError(
            f"artifact variant is not production-prebuilt: {artifact_id}"
        )
    if variant.get("development_command") not in (None, ""):
        raise RuntimeError(f"development command is forbidden for {artifact_id}")

    source_input = artifact_path.expanduser()
    if source_input.is_symlink():
        raise RuntimeError(
            f"release artifact is missing or symlinked: {artifact_path}"
        )
    source = source_input.resolve()
    if not source.exists():
        raise RuntimeError(f"release artifact is missing or symlinked: {artifact_path}")
    _reject_symlinks(source)
    _validate_entrypoint(source, str(variant.get("entrypoint") or ""))
    _validate_bundle_identity(source, variant.get("bundle_identifier"))
    _validate_macos_signature(source, str(variant.get("platform") or ""))

    output = output_dir.expanduser().resolve()
    if output.exists():
        raise RuntimeError(f"release artifact output already exists: {output}")
    output.mkdir(parents=True)
    staged = _copy_artifact(
        source,
        output / ARTIFACT_ROOT / artifact_id,
        str(variant["entrypoint"]),
    )
    digest = artifact_digest(staged)
    relative = staged.relative_to(output).as_posix()
    variant["path"] = relative
    variant["sha256"] = digest

    (output / "presentation_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "artifact_id": artifact_id,
        "path": relative,
        "sha256": digest,
        "output_dir": os.fspath(output),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run release artifact verification and staging."""
    args = parse_args(argv)
    report = package_artifact(
        args.catalog,
        args.artifact_id,
        args.artifact,
        args.output_dir,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
