#!/usr/bin/env python3
"""Materialize one build-produced Shell v4 artifact for a Launcher package.

The source catalog is only a declaration and deliberately contains no installed
paths.  This command consumes an exact build-output manifest after the Shell
build has completed, copies that artifact, and emits a signed catalog/index/lock
set.  Runtime discovery, PATH lookup, and development-command fallbacks are not
accepted.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib.util
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

try:
    from tobkiri_launcher.scripts.artifact_integrity import artifact_digest_and_size
except ModuleNotFoundError:
    from artifact_integrity import artifact_digest_and_size  # type: ignore[no-redef]

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_packaging_cleanup():
    """Load the canonical cleanup module without mutating import search paths."""
    helper_path = REPOSITORY_ROOT / "tobkiri_runtime/scripts/packaging_cleanup.py"
    spec = importlib.util.spec_from_file_location("tobkiri_packaging_cleanup", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"packaging cleanup helper is unavailable: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_PACKAGING_CLEANUP = _load_packaging_cleanup()
isolated_packaging_environment = _PACKAGING_CLEANUP.isolated_packaging_environment
isolated_python_module_command = _PACKAGING_CLEANUP.isolated_python_module_command
remove_owned_path = _PACKAGING_CLEANUP.remove_owned_path
run_process_and_wait = _PACKAGING_CLEANUP.run_process_and_wait


def _load_source_manifest_verifier():
    """Load canonical source-closure tools without search-path changes."""
    verifier_path = REPOSITORY_ROOT / "tobkiri_runtime/scripts/generator_source_manifest.py"
    spec = importlib.util.spec_from_file_location(
        "tobkiri_generator_source_manifest", verifier_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"source closure verifier is unavailable: {verifier_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.verify_source_closure, module.materialize_source_snapshot


verify_source_closure, materialize_source_snapshot = _load_source_manifest_verifier()


def artifact_digest(path: Path) -> str:
    """Return the canonical artifact digest for compatibility with callers."""
    return artifact_digest_and_size(path)[0]


def artifact_size(path: Path) -> int:
    """Return the canonical artifact payload size for compatibility with callers."""
    return artifact_digest_and_size(path)[1]

CATALOG_SCHEMA = "io.tobkiri.launcher.presentation-catalog.v1"
BUILD_OUTPUT_SCHEMA = "io.tobkiri.shell.build-output.v4"
ARTIFACT_INDEX_SCHEMA = "io.tobkiri.shell.artifact-index.v4"
PROFILE_LOCK_SCHEMA = "io.tobkiri.shell.profile-lock.v4"
RELEASE_SCHEMA = "io.tobkiri.shell.release.v4"
ARTIFACT_ROOT = Path("bundled/presentation-artifacts")
INDEX_PATH = Path("bundled/shell_artifact_index.v4.json")
LOCK_PATH = Path("bundled/shell_profile_lock.v4.json")
RELEASE_PATH = Path("bundled/presentation_release.v4.json")
DEFAULT_PROFILE_PATH = Path("ecosystem/defaultspack/v4/defaults.profile.v4.json")
DEFAULTSPACK_LOCK_PATH = Path("ecosystem/defaultspack/v4/bundle.lock.json")
INSTALLED_METADATA_FIELDS = (
    "path",
    "sha256",
    "entrypoint_sha256",
    "size",
    "source_identity",
    "source_revision",
)
VALID_TARGETS = {
    ("macos", "arm64"),
    ("macos", "x86_64"),
    ("windows", "x86_64"),
    ("linux", "x86_64"),
}
GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
WINDOWS_DRIVE_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:\\")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "CONIN$",
    "CONOUT$",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
    *(f"COM{index}" for index in "¹²³"),
    *(f"LPT{index}" for index in "¹²³"),
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse release materialization arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--build-output-manifest", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--signing-key-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        help="Checkout used only to materialize the verified source snapshot.",
    )
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--source-clean", action="store_true")
    return parser.parse_args(argv)


def canonical_json(value: Any) -> bytes:
    """Encode deterministic JSON used for revision and lock digests."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def json_digest(value: Any) -> str:
    """Return a canonical SHA-256 digest for a JSON value."""
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def file_digest(path: Path) -> str:
    """Return the SHA-256 digest of exact file bytes."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    """Write stable human-readable JSON and a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _load_object(path: Path, schema: str, label: str) -> dict[str, Any]:
    """Load a non-symlinked JSON object with the exact schema."""
    path = path.expanduser()
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} must be a regular non-symlink file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"failed to read {label} {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise RuntimeError(f"unsupported {label} schema: {path}")
    return value


def _required_text(value: Mapping[str, Any], name: str) -> str:
    """Read a required non-empty string field."""
    result = value.get(name)
    if not isinstance(result, str) or not result.strip():
        raise RuntimeError(f"build-output manifest field {name!r} is required")
    return result


def _validate_current_source(
    build_output: Mapping[str, Any],
    repository_root: Path | None,
    *,
    source_commit: str | None,
    source_tree: str | None,
    source_clean: bool | None,
) -> None:
    """Validate formal provenance without consulting checkout or Git metadata."""
    if repository_root is None:
        return
    if source_commit is None or source_tree is None or source_clean is not True:
        raise RuntimeError(
            "formal source provenance requires source commit, source tree, "
            "and source-clean=true"
        )
    if GIT_REVISION_RE.fullmatch(source_commit) is None or len(set(source_commit)) <= 1:
        raise RuntimeError("source commit must be a full lowercase 40-hex identity")
    if GIT_REVISION_RE.fullmatch(source_tree) is None or len(set(source_tree)) <= 1:
        raise RuntimeError("source tree must be a full lowercase 40-hex identity")
    if build_output.get("source_revision") != source_commit:
        raise RuntimeError(
            "build-output manifest source revision is stale: "
            f"expected {source_commit}, got {build_output.get('source_revision')!r}"
        )


def _validate_uninstalled_catalog(catalog: Mapping[str, Any]) -> None:
    """Require the tracked declaration, never a stale installed catalog, as input."""
    if catalog.get("release_binding") is not None:
        raise RuntimeError(
            "release packaging requires the uninstalled v4 catalog; old release "
            "metadata must not be reused"
        )
    default_selection = catalog.get("default_selection")
    if not isinstance(default_selection, Mapping):
        raise RuntimeError("presentation catalog has no exact default Profile selection")
    shells = catalog.get("shell_providers")
    if not isinstance(shells, list) or not shells:
        raise RuntimeError("presentation catalog has no Shell Providers")
    default_provider = default_selection.get("shell_provider_id")
    selected = [
        shell
        for shell in shells
        if isinstance(shell, Mapping) and shell.get("provider_id") == default_provider
    ]
    if len(selected) != 1:
        raise RuntimeError("presentation catalog default Profile Shell is not unique")
    for shell in shells:
        if not isinstance(shell, Mapping):
            raise RuntimeError("presentation catalog contains a malformed Shell Provider")
        variants = shell.get("artifact_variants")
        if not isinstance(variants, list) or not variants:
            raise RuntimeError("presentation catalog contains no Shell artifact variants")
        for variant in variants:
            if not isinstance(variant, Mapping):
                raise RuntimeError("presentation catalog contains a malformed artifact variant")
            if (variant.get("platform"), variant.get("architecture")) not in VALID_TARGETS:
                raise RuntimeError(
                    f"presentation catalog has an unsupported artifact target: "
                    f"{variant.get('platform')}/{variant.get('architecture')}"
                )
            if any(variant.get(field) is not None for field in INSTALLED_METADATA_FIELDS):
                raise RuntimeError(
                    f"presentation catalog contains stale installed metadata: "
                    f"{variant.get('artifact_id')}"
                )
            if variant.get("development_command") not in (None, ""):
                raise RuntimeError(
                    f"development command is forbidden for {variant.get('artifact_id')}"
                )


def _reject_symlinks(path: Path) -> None:
    """Reject symlinked release inputs and descendants."""
    if path.is_symlink():
        raise RuntimeError(f"release artifact may not be a symlink: {path}")
    if not path.is_dir():
        return
    for child in path.iterdir():
        _reject_symlinks(child)


def _reject_symlink_components(path: Path) -> None:
    """Reject symlinked or reparse-point components before resolving a path."""
    path = path.expanduser().absolute()
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        is_reparse_point = bool(attributes & reparse_flag)
        if (
            (current.is_symlink() or is_reparse_point)
            and current not in {Path("/var"), Path("/tmp")}
        ):
            raise RuntimeError(f"release artifact is missing or symlinked: {current}")


def _canonical_windows_absolute_artifact_path(
    value: str, repository_root: str
) -> PureWindowsPath:
    """Validate a native Windows manifest path without lossy normalization."""
    if (
        not WINDOWS_DRIVE_ABSOLUTE_RE.match(value)
        or "/" in value
        or "\x00" in value
        or value.startswith("~")
    ):
        raise RuntimeError(f"release artifact path is unsafe: {value}")
    declared = PureWindowsPath(value)
    if not declared.is_absolute() or str(declared) != value:
        raise RuntimeError(f"release artifact path is unsafe: {value}")
    for part in declared.parts[1:]:
        stem = part.split(".", 1)[0].upper()
        if (
            part in {"", ".", ".."}
            or part.endswith((" ", "."))
            or any(character in part for character in '<>:"|?*')
            or any(ord(character) < 32 for character in part)
            or stem in WINDOWS_RESERVED_NAMES
        ):
            raise RuntimeError(f"release artifact path is unsafe: {value}")

    root = PureWindowsPath(repository_root)
    if not root.is_absolute() or root.drive.casefold() != declared.drive.casefold():
        raise RuntimeError(f"release artifact path escapes its repository: {value}")
    if not declared.is_relative_to(root):
        raise RuntimeError(f"release artifact path escapes its repository: {value}")
    return declared


def _normalize_relative_path(value: str, field: str) -> str:
    """Normalize one package-relative path before it is used for I/O."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RuntimeError(f"{field} is unsafe: {value!r}")
    if value.startswith("~") or Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
        raise RuntimeError(f"{field} is unsafe: {value!r}")
    raw_parts = value.split("/")
    if any(part == ".." for part in raw_parts):
        raise RuntimeError(f"{field} is unsafe: {value!r}")
    parts = [part for part in raw_parts if part not in {"", "."}]
    if not parts:
        raise RuntimeError(f"{field} is unsafe: {value!r}")
    return "/".join(parts)


def _path_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    """Return the stable identity fields used for source snapshot checks."""
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
    )


def _snapshot_file(source: Path, destination: Path) -> None:
    """Copy one source file from an open descriptor into the transaction."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(os.fspath(source), flags)
    except OSError as error:
        raise RuntimeError(f"release artifact could not be snapshotted: {source}") from error
    try:
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise RuntimeError(f"release artifact is not a regular file: {source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output:
                size = 0
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    output.write(chunk)
                    size += len(chunk)
            after = os.fstat(handle.fileno())
    except OSError as error:
        raise RuntimeError(f"release artifact could not be snapshotted: {source}") from error
    if _path_identity(before) != _path_identity(after) or size != after.st_size:
        raise RuntimeError(f"release artifact changed while it was snapshotted: {source}")
    destination.chmod(stat.S_IMODE(after.st_mode))


def _stream_file_digest(path: Path) -> str:
    """Hash one regular file in bounded chunks with an identity check."""
    before = path.stat(follow_symlinks=False)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"release file is not regular: {path}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    after = path.stat(follow_symlinks=False)
    if _path_identity(before) != _path_identity(after) or size != after.st_size:
        raise RuntimeError(f"release file changed while it was hashed: {path}")
    return "sha256:" + digest.hexdigest()


def _snapshot_tree(source: Path, destination: Path) -> None:
    """Recursively snapshot a symlink-free source tree without reopening it."""
    before = source.stat(follow_symlinks=False)
    if source.is_symlink() or not stat.S_ISDIR(before.st_mode):
        raise RuntimeError(f"release artifact tree is not a real directory: {source}")
    destination.mkdir(parents=True, exist_ok=False)
    destination.chmod(stat.S_IMODE(before.st_mode))
    try:
        children = sorted(source.iterdir(), key=lambda item: item.name)
    except OSError as error:
        raise RuntimeError(f"release artifact could not be snapshotted: {source}") from error
    for child in children:
        if child.is_symlink():
            raise RuntimeError(f"release artifact may not contain a symlink: {child}")
        target = destination / child.name
        if child.is_dir():
            _snapshot_tree(child, target)
        elif child.is_file():
            _snapshot_file(child, target)
        else:
            raise RuntimeError(f"unsupported release artifact entry: {child}")
    after = source.stat(follow_symlinks=False)
    if _path_identity(before) != _path_identity(after):
        raise RuntimeError(f"release artifact changed while it was snapshotted: {source}")


def _snapshot_artifact(source: Path, destination: Path) -> Path:
    """Take the only source snapshot used by release validation and sealing."""
    if source.is_symlink() or not source.exists():
        raise RuntimeError(f"release artifact is missing or symlinked: {source}")
    if source.is_dir():
        _snapshot_tree(source, destination)
    elif source.is_file():
        _snapshot_file(source, destination)
    else:
        raise RuntimeError(f"unsupported release artifact: {source}")
    return destination


def _find_variant(
    catalog: Mapping[str, Any], artifact_id: str
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    for shell in catalog.get("shell_providers", []):
        if not isinstance(shell, Mapping):
            continue
        for variant in shell.get("artifact_variants", []):
            if isinstance(variant, dict) and variant.get("artifact_id") == artifact_id:
                return shell, variant
    raise RuntimeError(
        f"artifact variant is not declared in the catalog: {artifact_id}"
    )


def _validate_bundle_identity(artifact: Path, expected: str | None) -> None:
    if artifact.suffix != ".app":
        return
    if not isinstance(expected, str) or not expected.strip():
        raise RuntimeError("macOS .app artifact has no declared bundle identity")
    plist_path = artifact / "Contents" / "Info.plist"
    _reject_symlink_components(plist_path)
    if plist_path.is_symlink():
        raise RuntimeError("macOS artifact Info.plist may not be a symlink")
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


def _validate_entrypoint(artifact: Path, entrypoint: str) -> Path:
    normalized = _normalize_relative_path(entrypoint, "artifact entrypoint")
    entry = Path(normalized)
    if artifact.is_dir():
        candidate = (
            artifact / Path(*entry.parts[1:])
            if entry.parts[0] == artifact.name
            else artifact / entry
        )
    else:
        candidate = artifact
    if not candidate.is_file():
        raise RuntimeError(f"declared artifact entrypoint is missing: {candidate}")
    _reject_symlink_components(candidate)
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(artifact.resolve()):
        raise RuntimeError("declared artifact entrypoint escapes its artifact")
    if not (candidate.stat().st_mode & stat.S_IXUSR):
        raise RuntimeError(
            f"declared artifact entrypoint is not executable: {candidate}"
        )
    return candidate


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(stat.S_IMODE(source.stat().st_mode))


def _copy_tree(source: Path, destination: Path) -> None:
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


def _copy_artifact(source: Path, destination_dir: Path, entrypoint: str) -> Path:
    """Copy a snapshotted artifact using a normalized entrypoint root."""
    normalized = _normalize_relative_path(entrypoint, "artifact entrypoint")
    _validate_entrypoint(source, normalized)
    destination_dir.mkdir(parents=True, exist_ok=False)
    destination = destination_dir / (
        Path(normalized).parts[0] if source.is_dir() else Path(normalized).name
    )
    if source.is_dir():
        _copy_tree(source, destination)
    else:
        _copy_file(source, destination)
    _reject_symlinks(destination)
    return destination


def _read_bounded_header(path: Path) -> tuple[bytes, bytes | None]:
    """Read only the bounded header needed for architecture validation."""
    before = path.stat(follow_symlinks=False)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("entrypoint is not a regular file")
    with path.open("rb") as handle:
        prefix = handle.read(64)
        pe_header: bytes | None = None
        if prefix[:2] == b"MZ":
            if len(prefix) >= 64:
                pe_offset = int.from_bytes(prefix[60:64], "little")
                if pe_offset < 64 or pe_offset > before.st_size - 24:
                    raise RuntimeError("PE entrypoint header is out of bounds")
                handle.seek(pe_offset)
                pe_header = handle.read(24)
                if len(pe_header) < 24 or pe_header[:4] != b"PE\0\0":
                    raise RuntimeError("PE entrypoint signature is invalid or truncated")
    after = path.stat(follow_symlinks=False)
    if _path_identity(before) != _path_identity(after):
        raise RuntimeError("entrypoint changed while its header was verified")
    return prefix, pe_header


def _validate_binary_architecture(entrypoint: Path, architecture: str) -> None:
    """Validate recognized ELF, Mach-O, and PE headers with safe bounds."""
    payload, pe_header = _read_bounded_header(entrypoint)
    actual: str | None = None
    if payload[:4] in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"}:
        if len(payload) < 8:
            raise RuntimeError("Mach-O entrypoint header is truncated")
        machine = int.from_bytes(
            payload[4:8],
            "little" if payload[:4] == b"\xcf\xfa\xed\xfe" else "big",
        )
        actual = {0x01000007: "x86_64", 0x0100000C: "arm64"}.get(machine)
        if actual is None:
            raise RuntimeError("Mach-O entrypoint has an unsupported machine")
    elif payload[:4] == b"\x7fELF":
        if len(payload) < 20:
            raise RuntimeError("ELF entrypoint header is truncated")
        machine = int.from_bytes(
            payload[18:20], "little" if payload[5:6] == b"\x01" else "big"
        )
        actual = {62: "x86_64", 183: "arm64"}.get(machine)
        if actual is None:
            raise RuntimeError("ELF entrypoint has an unsupported machine")
    elif payload[:2] == b"MZ":
        # A short MZ-stub is retained for the repository's format-agnostic
        # fixtures. Once e_lfanew is present, however, it is a PE claim and
        # every boundary is checked before the COFF machine is read.
        if pe_header is None:
            return
        machine = int.from_bytes(pe_header[4:6], "little")
        actual = {0x8664: "x86_64", 0xAA64: "arm64"}.get(machine)
        if actual is None:
            raise RuntimeError("PE entrypoint has an unsupported machine")
    if actual is not None and actual != architecture:
        raise RuntimeError(
            f"entrypoint architecture does not match release target: "
            f"expected {architecture}, got {actual}"
        )


def _new_staging_directory(parent: Path, prefix: str) -> Path:
    """Create owner-only staging on the output filesystem."""
    parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(parent)
    staging = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    staging.chmod(0o700)
    return staging


def _make_owned_tree_writable(path: Path) -> None:
    """Make an owned, link-free staging tree writable without following links."""
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"owned staging tree is not a real directory: {path}")
    for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        metadata = child.stat(follow_symlinks=False)
        if child.is_symlink() or not (
            stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)
        ):
            raise RuntimeError(f"owned staging tree contains an unsafe entry: {child}")
        mode = stat.S_IMODE(metadata.st_mode)
        child.chmod(mode | (0o700 if stat.S_ISDIR(metadata.st_mode) else 0o600))
    path.chmod(stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) | 0o700)


def _remove_tree(path: Path) -> None:
    """Remove only a transaction-owned path during cleanup."""
    if path.exists() and not path.is_symlink():
        # Source snapshots are deliberately non-writable while a child uses
        # them.  Once the child has exited, make only this owned transaction
        # removable before handing it to the descriptor-relative cleanup
        # walker; the immutable snapshot is never reused after this point.
        for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            metadata = child.stat(follow_symlinks=False)
            if child.is_symlink() or not (
                stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)
            ):
                raise RuntimeError(f"owned transaction contains an unsafe entry: {child}")
            mode = stat.S_IMODE(metadata.st_mode)
            child.chmod(mode | (0o300 if stat.S_ISDIR(metadata.st_mode) else 0o200))
        path.chmod(stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) | 0o300)
    remove_owned_path(
        path,
        owner_root=path.parent,
        operation="remove presentation packaging transaction path",
    )


def _publish_directory(staging: Path, output: Path) -> None:
    """Replace an output directory with rollback if either rename fails."""
    parent = output.parent
    backup: Path | None = None
    existing = output.exists() or output.is_symlink()
    if existing:
        if output.is_symlink() or not output.is_dir():
            raise RuntimeError(f"release artifact output must be a directory: {output}")
        backup = Path(tempfile.mkdtemp(prefix=f".{output.name}.rollback-", dir=parent))
        _remove_tree(backup)
        moved_existing = False
        published = False
        try:
            os.replace(output, backup)
            moved_existing = True
            os.replace(staging, output)
            published = True
        except Exception:
            if published and (output.exists() or output.is_symlink()):
                _remove_tree(output)
            if moved_existing and backup.exists():
                os.replace(backup, output)
            raise
    else:
        published = False
        try:
            os.replace(staging, output)
            published = True
        except Exception:
            if published and (output.exists() or output.is_symlink()):
                _remove_tree(output)
            raise
    if backup is not None and (backup.exists() or backup.is_symlink()):
        _remove_tree(backup)


def _verify_staged_release(
    root: Path,
    *,
    artifact_id: str,
    platform: str,
    architecture: str,
    source_identity: str,
    source_revision: str,
    signing_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    """Re-read every staged binding and verify it before publication."""
    catalog_path = root / "presentation_catalog.json"
    index_path = root / INDEX_PATH
    lock_path = root / LOCK_PATH
    release_path = root / RELEASE_PATH
    catalog = _load_object(catalog_path, CATALOG_SCHEMA, "staged presentation catalog")
    index = _load_object(index_path, ARTIFACT_INDEX_SCHEMA, "staged artifact index")
    lock = _load_object(lock_path, PROFILE_LOCK_SCHEMA, "staged profile lock")
    release = _load_object(release_path, RELEASE_SCHEMA, "staged release manifest")
    release_fields = {
        "schema",
        "catalog_path",
        "catalog_sha256",
        "artifact_index_path",
        "artifact_index_sha256",
        "profile_lock_path",
        "profile_lock_sha256",
        "default_profile_path",
        "default_profile_sha256",
        "defaultspack_lock_path",
        "defaultspack_lock_sha256",
        "artifact_id",
        "platform",
        "architecture",
        "source_identity",
        "source_revision",
        "key_id",
        "public_key",
        "signature",
    }
    if set(release) != release_fields:
        raise RuntimeError("staged release manifest has unknown or missing fields")

    shell, variant = _find_variant(catalog, artifact_id)
    expected_path = index.get("path")
    if not isinstance(expected_path, str):
        raise RuntimeError("staged artifact index path is not text")
    normalized_path = _normalize_relative_path(expected_path, "staged artifact path")
    if not normalized_path.startswith("bundled/presentation-artifacts/"):
        raise RuntimeError("staged artifact path is outside presentation-artifacts")
    artifact = root / Path(*normalized_path.split("/"))
    _reject_symlink_components(artifact)
    if artifact.is_symlink() or not artifact.exists():
        raise RuntimeError("staged artifact path is missing or symlinked")

    digest, size = artifact_digest_and_size(artifact)
    if digest != index.get("sha256") or size != index.get("size"):
        raise RuntimeError("staged artifact digest or size does not match its index")
    entrypoint_value = variant.get("entrypoint")
    if not isinstance(entrypoint_value, str):
        raise RuntimeError("staged artifact entrypoint is missing")
    entrypoint = _validate_entrypoint(artifact, entrypoint_value)
    entrypoint_digest = _stream_file_digest(entrypoint)
    if entrypoint_digest != index.get("entrypoint_sha256"):
        raise RuntimeError("staged artifact entrypoint digest does not match its index")
    _validate_binary_architecture(entrypoint, architecture)
    _validate_bundle_identity(artifact, variant.get("bundle_identifier"))
    _validate_macos_signature(artifact, platform)

    exact_fields = {
        "artifact_id": artifact_id,
        "platform": platform,
        "architecture": architecture,
        "source_identity": source_identity,
        "source_revision": source_revision,
    }
    for field, expected in exact_fields.items():
        if index.get(field) != expected or lock.get(field) != expected:
            raise RuntimeError(f"staged release field mismatch: {field}")
        if field != "artifact_id" and variant.get(field) != expected:
            raise RuntimeError(f"staged catalog field mismatch: {field}")
    for field in ("path", "sha256", "entrypoint_sha256", "size"):
        if variant.get(field) != index.get(field):
            raise RuntimeError(f"staged catalog/index mismatch: {field}")
    if shell.get("provider_id") != catalog.get("default_selection", {}).get(
        "shell_provider_id"
    ):
        raise RuntimeError("staged artifact does not match the default Profile Shell")
    if lock.get("artifact_sha256") != digest or lock.get("entrypoint_sha256") != entrypoint_digest:
        raise RuntimeError("staged profile lock artifact binding mismatch")
    lock_body = {key: value for key, value in lock.items() if key != "lock_revision"}
    if json_digest(lock_body) != lock.get("lock_revision"):
        raise RuntimeError("staged profile lock revision mismatch")
    index_digest = json_digest(index)
    if lock.get("artifact_index_sha256") != index_digest:
        raise RuntimeError("staged profile lock index binding mismatch")
    catalog_without_binding = {
        key: value for key, value in catalog.items() if key != "release_binding"
    }
    catalog_revision = json_digest(catalog_without_binding)
    binding = catalog.get("release_binding")
    if not isinstance(binding, Mapping):
        raise RuntimeError("staged catalog has no release binding")
    if binding.get("catalog_revision") != catalog_revision:
        raise RuntimeError("staged catalog revision mismatch")
    if binding.get("artifact_index_sha256") != index_digest:
        raise RuntimeError("staged catalog index binding mismatch")
    if binding.get("profile_lock_sha256") != json_digest(lock):
        raise RuntimeError("staged catalog profile lock binding mismatch")

    if release.get("catalog_path") != "bundled/presentation_catalog.json":
        raise RuntimeError("staged release catalog path is not canonical")
    if release.get("artifact_index_path") != INDEX_PATH.as_posix():
        raise RuntimeError("staged release artifact index path is not canonical")
    if release.get("profile_lock_path") != LOCK_PATH.as_posix():
        raise RuntimeError("staged release profile lock path is not canonical")
    expected_release = {
        "catalog_sha256": file_digest(catalog_path),
        "artifact_index_sha256": file_digest(index_path),
        "profile_lock_sha256": file_digest(lock_path),
        **exact_fields,
    }
    if release.get("default_profile_path") != DEFAULT_PROFILE_PATH.as_posix():
        raise RuntimeError("staged release Profile path is not canonical")
    if release.get("defaultspack_lock_path") != DEFAULTSPACK_LOCK_PATH.as_posix():
        raise RuntimeError("staged release Defaults lock path is not canonical")
    profile_digest = release.get("default_profile_sha256")
    lock_digest = release.get("defaultspack_lock_sha256")
    if catalog.get("default_profile_digest") != profile_digest:
        raise RuntimeError("staged catalog Profile identity differs from release")
    for value, label in (
        (profile_digest, "default Profile"),
        (lock_digest, "Defaults bundle lock"),
    ):
        if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
            raise RuntimeError(f"staged release {label} digest is invalid")
    for field, expected in expected_release.items():
        if release.get(field) != expected:
            raise RuntimeError(f"staged release manifest mismatch: {field}")
    try:
        public_key = base64.b64decode(release["public_key"], validate=True)
        signature = base64.b64decode(release["signature"], validate=True)
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, _signature_message(release)
        )
    except (KeyError, TypeError, ValueError, binascii.Error, InvalidSignature) as error:
        raise RuntimeError("staged release signature verification failed") from error
    expected_public_key = signing_key.public_key().public_bytes_raw()
    if public_key != expected_public_key:
        raise RuntimeError("staged release public key does not match signing key")
    return {
        "catalog_sha256": expected_release["catalog_sha256"],
        "artifact_index_sha256": expected_release["artifact_index_sha256"],
        "profile_lock_sha256": expected_release["profile_lock_sha256"],
    }


def _signature_message(release: Mapping[str, Any]) -> bytes:
    """Return the cross-language fixed-field Ed25519 message."""
    fields = (
        RELEASE_SCHEMA,
        str(release["catalog_sha256"]),
        str(release["artifact_index_sha256"]),
        str(release["profile_lock_sha256"]),
        str(release["default_profile_sha256"]),
        str(release["defaultspack_lock_sha256"]),
        str(release["source_identity"]),
        str(release["source_revision"]),
        str(release["platform"]),
        str(release["architecture"]),
        str(release["artifact_id"]),
        str(release["key_id"]),
    )
    return b"\0".join(field.encode("utf-8") for field in fields)


def _project_packaged_defaultspack(
    *,
    repository_root: Path,
    source_artifact: Path,
    artifact_ref: str,
    entrypoint: str,
    platform: str,
    architecture: str,
    bundle_identity: str,
    source_revision: str,
    source_tree: str,
    source_clean: bool,
    transaction_root: Path,
) -> dict[str, Any]:
    """Generate the exact packaged Profile projection before release signing."""
    source_root = repository_root / "tobkiri_runtime"
    if source_root.is_symlink() or not source_root.is_dir():
        raise RuntimeError(f"canonical runtime source is unavailable: {source_root}")
    bundle_root = transaction_root / "v4"
    artifact_root = transaction_root / "platform-artifacts"
    source_snapshot_root = transaction_root / "source-snapshot" / "tobkiri_runtime"
    verify_source_closure(source_root)
    materialize_source_snapshot(source_root, source_snapshot_root)
    source_bundle = source_snapshot_root / "ecosystem/defaultspack/v4"
    shutil.copytree(source_bundle, bundle_root)
    _make_owned_tree_writable(bundle_root)
    run_process_and_wait(
        isolated_python_module_command(
            sys.executable,
            "scripts.generate_packaged_defaultspack_v4_bundle",
            source_snapshot_root,
            [
                "--source-artifact",
                os.fspath(source_artifact),
                "--bundle-root",
                os.fspath(bundle_root),
                "--artifact-root",
                os.fspath(artifact_root),
                "--relative-path",
                artifact_ref,
                "--entrypoint",
                entrypoint,
                "--platform",
                platform,
                "--architecture",
                architecture,
                "--bundle-identity",
                bundle_identity,
                "--source-commit",
                source_revision,
                "--source-tree",
                source_tree,
                "--source-clean",
                "--source-snapshot-root",
                os.fspath(source_snapshot_root),
            ],
        ),
        cwd=source_snapshot_root,
        env=isolated_packaging_environment(),
    )
    profile = bundle_root / "defaults.profile.v4.json"
    lock_path = bundle_root / "bundle.lock.json"
    lock = _load_object(
        lock_path,
        "io.tobkiri.defaultspack-bundle-lock.v1",
        "packaged Defaults v4 bundle lock",
    )
    source_manifest_digests: dict[str, str] = {}
    entries = lock.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("packaged Defaults v4 bundle lock entries are missing")
    paths = [entry.get("path") for entry in entries if isinstance(entry, Mapping)]
    kind_order = {"pack": 0, "base": 1, "shell": 2, "profile": 3}
    canonical_entries = sorted(
        entries,
        key=lambda entry: (
            kind_order.get(str(entry.get("kind")), 99),
            str(entry.get("path")),
        ),
    )
    if (
        len(paths) != len(entries)
        or entries != canonical_entries
        or len(set(paths)) != len(paths)
    ):
        raise RuntimeError("packaged Defaults v4 bundle lock order is not canonical")
    profile_digest = file_digest(profile)
    profile_entries = [
        entry
        for entry in entries
        if entry.get("path") == "defaults.profile.v4.json"
        and entry.get("kind") == "profile"
    ]
    if len(profile_entries) != 1 or profile_entries[0].get("digest") != profile_digest:
        raise RuntimeError("packaged Defaults lock does not bind the default Profile")
    for entry in entries:
        if not isinstance(entry, Mapping) or entry.get("kind") != "pack":
            continue
        relative = _normalize_relative_path(
            str(entry.get("path") or ""), "packaged bundle Pack path"
        )
        pack_path = bundle_root / relative
        if pack_path.is_symlink() or not pack_path.is_file():
            raise RuntimeError(f"packaged Pack is unavailable: {pack_path}")
        try:
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"packaged Pack is malformed: {pack_path}") from error
        if not isinstance(pack, dict):
            raise RuntimeError(f"packaged Pack is not an object: {pack_path}")
        pack_id = pack.get("pack", {}).get("id")
        digest = entry.get("digest")
        if not isinstance(pack_id, str) or not isinstance(digest, str):
            raise RuntimeError("packaged bundle Pack identity is incomplete")
        source_manifest_digests[pack_id] = digest
    return {
        "default_profile_sha256": profile_digest,
        "defaultspack_lock_sha256": file_digest(lock_path),
        "default_profile_bytes": profile.read_bytes(),
        "defaultspack_lock_bytes": lock_path.read_bytes(),
        "source_manifest_digests": source_manifest_digests,
    }


def _load_signing_key(path: Path) -> Ed25519PrivateKey:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"signing key must be a regular non-symlink file: {path}")
    raw = path.read_bytes()
    if len(raw) != 32:
        raise RuntimeError("Ed25519 signing key must contain exactly 32 raw seed bytes")
    return Ed25519PrivateKey.from_private_bytes(raw)


def package_artifact(
    catalog_path: Path,
    build_output_manifest: Path,
    signing_key_path: Path,
    signing_key_id: str,
    output_dir: Path,
    repository_root: Path | None = None,
    source_commit: str | None = None,
    source_tree: str | None = None,
    source_clean: bool | None = None,
) -> dict[str, Any]:
    """Verify and atomically bind one exact build output into a Shell v4 release."""
    if not signing_key_id.strip():
        raise RuntimeError("signing key id is required")
    catalog_path = catalog_path.expanduser().absolute()
    catalog = _load_object(
        catalog_path, CATALOG_SCHEMA, "presentation catalog"
    )
    _validate_uninstalled_catalog(catalog)
    manifest_path = build_output_manifest.expanduser().absolute()
    build_output = _load_object(
        manifest_path, BUILD_OUTPUT_SCHEMA, "build-output manifest"
    )
    _validate_current_source(
        build_output,
        repository_root,
        source_commit=source_commit,
        source_tree=source_tree,
        source_clean=source_clean,
    )
    artifact_id = _required_text(build_output, "artifact_id")
    platform = _required_text(build_output, "platform")
    architecture = _required_text(build_output, "architecture")
    source_identity = _required_text(build_output, "source_identity")
    source_revision = _required_text(build_output, "source_revision")
    artifact_value = _required_text(build_output, "artifact_path")
    if GIT_REVISION_RE.fullmatch(source_revision) is None:
        raise RuntimeError("source_revision must be a full 40-character Git commit SHA")
    if build_output.get("build_profile") != "release":
        raise RuntimeError("build-output manifest must identify a release build")
    if (platform, architecture) not in VALID_TARGETS:
        raise RuntimeError(
            f"build-output manifest has an unsupported platform/architecture: "
            f"{platform}/{architecture}"
        )

    shell, variant = _find_variant(catalog, artifact_id)
    default_selection = catalog.get("default_selection")
    if not isinstance(default_selection, Mapping):
        raise RuntimeError("presentation catalog has no exact default Profile selection")
    if shell.get("provider_id") != default_selection.get("shell_provider_id"):
        raise RuntimeError(
            "build-output artifact does not match the default Profile Shell"
        )
    if (
        variant.get("platform") != platform
        or variant.get("architecture") != architecture
    ):
        raise RuntimeError(
            "build-output platform/architecture does not match the declared variant"
        )
    expected_artifact_id = f"{shell.get('provider_id')}.{platform}-{architecture}"
    if artifact_id != expected_artifact_id:
        raise RuntimeError(
            "build-output artifact identity does not match its Shell and target"
        )
    if variant.get("prebuilt") is not True or variant.get("production") is not True:
        raise RuntimeError(
            f"artifact variant is not production-prebuilt: {artifact_id}"
        )
    if variant.get("development_command") not in (None, ""):
        raise RuntimeError(f"development command is forbidden for {artifact_id}")

    if platform == "windows" and os.name == "nt" and "/" in artifact_value:
        raise RuntimeError(f"release artifact path is unsafe: {artifact_value}")
    if "\\" in artifact_value:
        if platform != "windows" or os.name != "nt" or repository_root is None:
            raise RuntimeError(f"release artifact path is unsafe: {artifact_value}")
        repository_input = repository_root.expanduser().absolute()
        _reject_symlink_components(repository_input)
        try:
            repository_source = repository_input.resolve(strict=True)
        except OSError as error:
            raise RuntimeError(
                f"release repository root is missing or symlinked: {repository_input}"
            ) from error
        _canonical_windows_absolute_artifact_path(
            artifact_value, os.fspath(repository_source)
        )
        source_input = Path(artifact_value)
    else:
        if artifact_value.startswith("~") or "\x00" in artifact_value:
            raise RuntimeError(f"release artifact path is unsafe: {artifact_value}")
        declared_path = Path(artifact_value)
        if declared_path.is_absolute():
            source_input = declared_path
        else:
            if ".." in declared_path.parts:
                raise RuntimeError(
                    f"release artifact path escapes its manifest: {artifact_value}"
                )
            source_input = manifest_path.parent / declared_path
    source_input = source_input.expanduser().absolute()
    _reject_symlink_components(source_input)
    if source_input.is_symlink():
        raise RuntimeError(f"release artifact is missing or symlinked: {source_input}")
    try:
        source = source_input.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(
            f"release artifact is missing or symlinked: {source_input}"
        ) from error
    if not source.exists():
        raise RuntimeError(f"release artifact is missing or symlinked: {source_input}")
    if "\\" in artifact_value:
        if not source.is_relative_to(repository_source):
            raise RuntimeError(
                f"release artifact path escapes its repository: {artifact_value}"
            )
    signing_key = _load_signing_key(signing_key_path.expanduser())
    entrypoint = _normalize_relative_path(
        str(variant.get("entrypoint") or ""), "artifact entrypoint"
    )
    _validate_entrypoint(source, entrypoint)
    _validate_bundle_identity(source, variant.get("bundle_identifier"))
    _validate_macos_signature(source, platform)
    _validate_binary_architecture(_validate_entrypoint(source, entrypoint), architecture)

    if repository_root is None:
        raise RuntimeError(
            "repository_root is required to bind the packaged Defaults v4 identity"
        )
    repository = repository_root.expanduser().resolve(strict=True)
    canonical_catalog = (
        repository / "tobkiri_launcher/src-tauri/bundled/presentation_catalog.json"
    )
    if (
        canonical_catalog.is_symlink()
        or not canonical_catalog.is_file()
        or catalog_path.resolve(strict=True) != canonical_catalog.resolve(strict=True)
    ):
        raise RuntimeError("presentation catalog must be the canonical checkout catalog")

    output = output_dir.expanduser().absolute()
    _reject_symlink_components(output.parent)
    if output.is_symlink():
        raise RuntimeError(f"release artifact output may not be a symlink: {output}")
    staging: Path | None = _new_staging_directory(
        output.parent, ".tobkiri-presentation-stage-"
    )
    try:
        assert staging is not None
        snapshot_parent = staging / "source-snapshot"
        snapshot = snapshot_parent / source.name
        _snapshot_artifact(source, snapshot)

        if platform == "macos" and snapshot.suffix != ".app":
            raise RuntimeError("macOS Shell release artifact must be an .app bundle")

        staged = _copy_artifact(
            snapshot,
            staging / ARTIFACT_ROOT / artifact_id,
            entrypoint,
        )
        _remove_tree(snapshot_parent)
        _validate_entrypoint(staged, entrypoint)
        _validate_bundle_identity(staged, variant.get("bundle_identifier"))
        _validate_macos_signature(staged, platform)
        entrypoint_path = _validate_entrypoint(staged, entrypoint)
        _validate_binary_architecture(entrypoint_path, architecture)
        digest, size = artifact_digest_and_size(staged)
        entrypoint_digest = _stream_file_digest(entrypoint_path)
        relative = staged.relative_to(staging).as_posix()
        variant.update(
            path=relative,
            sha256=digest,
            entrypoint_sha256=entrypoint_digest,
            size=size,
            source_identity=source_identity,
            source_revision=source_revision,
        )

        packaged_projection: dict[str, Any] | None = None
        if repository_root is not None:
            artifact_ref = _normalize_relative_path(
                str(variant.get("artifact_ref") or ""), "Shell artifact ref"
            )
            bundle_identity = _required_text(variant, "bundle_identifier")
            projection_root = Path(
                tempfile.mkdtemp(
                    prefix=".tobkiri-defaultspack-projection-", dir=output.parent
                )
            )
            try:
                packaged_projection = _project_packaged_defaultspack(
                    repository_root=repository,
                    source_artifact=staged,
                    artifact_ref=artifact_ref,
                    entrypoint=entrypoint,
                    platform=platform,
                    architecture=architecture,
                    bundle_identity=bundle_identity,
                    source_revision=source_revision,
                    source_tree=source_tree,
                    source_clean=bool(source_clean),
                    transaction_root=projection_root,
                )
            finally:
                _remove_tree(projection_root)
            catalog["default_profile_digest"] = packaged_projection[
                "default_profile_sha256"
            ]
            selected_digests = catalog.get("source_manifest_digests")
            if not isinstance(selected_digests, dict):
                raise RuntimeError("presentation catalog source manifest digests are missing")
            projected_digests = packaged_projection["source_manifest_digests"]
            for pack_id in tuple(selected_digests):
                if pack_id not in projected_digests:
                    raise RuntimeError(
                        f"packaged bundle is missing selected Pack: {pack_id}"
                    )
                selected_digests[pack_id] = projected_digests[pack_id]
            profile_output = staging / DEFAULT_PROFILE_PATH
            lock_output = staging / DEFAULTSPACK_LOCK_PATH
            profile_output.parent.mkdir(parents=True, exist_ok=True)
            profile_output.write_bytes(packaged_projection["default_profile_bytes"])
            lock_output.write_bytes(packaged_projection["defaultspack_lock_bytes"])

        index = {
            "schema": ARTIFACT_INDEX_SCHEMA,
            "artifact_id": artifact_id,
            "path": relative,
            "sha256": digest,
            "entrypoint_sha256": entrypoint_digest,
            "size": size,
            "platform": platform,
            "architecture": architecture,
            "source_identity": source_identity,
            "source_revision": source_revision,
        }
        index_digest = json_digest(index)
        catalog_revision = json_digest(catalog)
        lock_body = {
            "schema": PROFILE_LOCK_SCHEMA,
            "catalog_revision": catalog_revision,
            "artifact_index_sha256": index_digest,
            "artifact_id": artifact_id,
            "artifact_sha256": digest,
            "entrypoint_sha256": entrypoint_digest,
            "platform": platform,
            "architecture": architecture,
            "source_identity": source_identity,
            "source_revision": source_revision,
        }
        lock = {**lock_body, "lock_revision": json_digest(lock_body)}
        catalog["release_binding"] = {
            "schema": RELEASE_SCHEMA,
            "artifact_index_path": INDEX_PATH.as_posix(),
            "artifact_index_sha256": index_digest,
            "profile_lock_path": LOCK_PATH.as_posix(),
            "profile_lock_sha256": json_digest(lock),
            "catalog_revision": catalog_revision,
            "artifact_id": artifact_id,
            "source_identity": source_identity,
            "source_revision": source_revision,
            "platform": platform,
            "architecture": architecture,
        }

        catalog_output = staging / "presentation_catalog.json"
        _write_json(staging / INDEX_PATH, index)
        _write_json(staging / LOCK_PATH, lock)
        _write_json(catalog_output, catalog)
        release = {
            "schema": RELEASE_SCHEMA,
            "catalog_path": "bundled/presentation_catalog.json",
            "catalog_sha256": file_digest(catalog_output),
            "artifact_index_path": INDEX_PATH.as_posix(),
            "artifact_index_sha256": file_digest(staging / INDEX_PATH),
            "profile_lock_path": LOCK_PATH.as_posix(),
            "profile_lock_sha256": file_digest(staging / LOCK_PATH),
            "artifact_id": artifact_id,
            "platform": platform,
            "architecture": architecture,
            "source_identity": source_identity,
            "source_revision": source_revision,
            "key_id": signing_key_id,
        }
        if packaged_projection is not None:
            release.update(
                default_profile_path=DEFAULT_PROFILE_PATH.as_posix(),
                default_profile_sha256=packaged_projection[
                    "default_profile_sha256"
                ],
                defaultspack_lock_path=DEFAULTSPACK_LOCK_PATH.as_posix(),
                defaultspack_lock_sha256=packaged_projection[
                    "defaultspack_lock_sha256"
                ],
            )
        public_key = signing_key.public_key().public_bytes_raw()
        release["public_key"] = base64.b64encode(public_key).decode("ascii")
        release["signature"] = base64.b64encode(
            signing_key.sign(_signature_message(release))
        ).decode("ascii")
        _write_json(staging / RELEASE_PATH, release)
        _verify_staged_release(
            staging,
            artifact_id=artifact_id,
            platform=platform,
            architecture=architecture,
            source_identity=source_identity,
            source_revision=source_revision,
            signing_key=signing_key,
        )
        report = {
            "artifact_id": artifact_id,
            "path": relative,
            "sha256": digest,
            "entrypoint_sha256": entrypoint_digest,
            "size": size,
            "platform": platform,
            "architecture": architecture,
            "source_identity": source_identity,
            "source_revision": source_revision,
            "catalog_sha256": release["catalog_sha256"],
            "output_dir": os.fspath(output),
        }
        _publish_directory(staging, output)
        staging = None
        return report
    finally:
        if staging is not None and (staging.exists() or staging.is_symlink()):
            _remove_tree(staging)


def main(argv: Sequence[str] | None = None) -> int:
    """Run release artifact verification and materialization."""
    args = parse_args(argv)
    report = package_artifact(
        args.catalog,
        args.build_output_manifest,
        args.signing_key,
        args.signing_key_id,
        args.output_dir,
        args.repository_root,
        args.source_commit,
        args.source_tree,
        args.source_clean,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
