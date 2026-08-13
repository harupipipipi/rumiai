#!/usr/bin/env python3
"""Build and verify Tobkiri's fixed-layout sealed Python environment.

The release build runs on the native CI runner for one supported target.  It
uses the repository's pinned ``uv`` binary, the exact CPython patch version,
and the hash-locked runtime requirements export.  The resulting private tree
is passed directly to the Rust build through its absolute snapshot binding;
the mutable checkout is never used as the runtime source.

``--check`` is intentionally network-free.  It validates a small synthetic
fixture just as it validates a release tree, including the strict manifest,
all file hashes, the environment digest, sentinels, fixed entrypoints, and
the native Python prefix when the requested target is the current host.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import posixpath
import platform as host_platform
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
SEALED_SOURCE_ROOT = SCRIPT_DIR / "sealed_python_sources"
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
APP_SOURCE_ROOT = "tobkiri_runtime"
DEFAULT_OUTPUT_RELATIVE = Path("tobkiri_runtime/python-runtime")
DEFAULT_REQUIREMENTS_RELATIVE = Path("tobkiri_runtime/requirements.txt")
MANIFEST_FILENAME = "sealed-environment.v1.json"
SOURCE_SNAPSHOT_MANIFEST = ".tobkiri-source-snapshot.v1.json"
SOURCE_SNAPSHOT_SCHEMA = "io.tobkiri.rootless-source-snapshot.v1"
MANIFEST_SCHEMA = "io.tobkiri.sealed-python-environment.v1"
ATTESTATION_SCHEMA = "io.tobkiri.sealed-python-attestation.v1"
MANIFEST_SHA_ENV = "TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256"
LEASE_FILENAME = "lease.v1"
LEASE_CONTENT = "io.tobkiri.sealed-python-lease.v1\n"
UV_VERSION = "0.11.14"
PYTHON_VERSION = "3.13.13"
PYTHON_BUILD_REVISION = "20260510"
PACKAGE_ID = "dev.tobkiri.launcher"
UV_ARCHIVE_SHA256_BY_TARGET = {
    "aarch64-apple-darwin": "4333af5c0730d94323a7819bbdf87ce92dd07fc857d67fff0059e0fca31b5c02",
    "x86_64-apple-darwin": "9836c1440b0bd6aa5f81793648a339bd01d593b7b8f575de3b855dae4ab64654",
    "x86_64-pc-windows-msvc": "52ba5d19409aaa688a8a1a6ec8dfb6a4817230d20186e75f4006105c3e39a846",
    "x86_64-unknown-linux-gnu": "f3b623eb0e6141a7053d571d59a0bdc341e0f238ea8f5f0b4815ddbec9a2a296",
}
UV_BINARY_SHA256_BY_TARGET = {
    "aarch64-apple-darwin": "77b80ca26ad2142c50b870c730d9b8f617665720f09888630257b40d0678e658",
    "x86_64-apple-darwin": "1bb756786175621eea70219911d02bf8d3e32203bb5a7a19b345e44d031f436e",
    "x86_64-pc-windows-msvc": "442b73298cf8648217e5bc232588bb1067f98ea5b40beea18e43c9c7929c020c",
    "x86_64-unknown-linux-gnu": "b5cbc3a3f35debad0b4770811efd190bcf460b654114d6a3f71e0ce298468e5d",
}
PYTHON_ARCHIVE_SHA256_BY_TARGET = {
    "aarch64-apple-darwin": "16d2332d950178968534e65fe09f01f876d13af1147176fd0c77a74c9e4d1a4b",
    "x86_64-apple-darwin": "8937475b0b8536d391270da4510488cb41ecd21040b63f9d8f84a8b1cdd491fc",
}
PACKAGE_KIND_BY_PLATFORM = {
    "macos": "pinned-python-build-standalone-v1",
    "windows": "windows-authenticode-v1",
    "linux": "linux-immutable-package-v1",
}
REPARSE_POINT = 0x0400
IMMUTABLE_DIRECTORY_MODE = 0o555
IMMUTABLE_FILE_MODE = 0o444
IMMUTABLE_EXECUTABLE_MODE = 0o555
MANIFEST_KEYS = (
    "schema",
    "environment_digest",
    "platform",
    "architecture",
    "python_version",
    "package_provenance",
    "sentinels",
    "files",
)
FILE_KEYS = ("path", "size", "sha256", "executable")
SENTINEL_KEYS = ("stdlib_sha256", "site_packages_sha256", "native_sha256")
SENTINEL_FILENAMES = {
    "stdlib_sha256": "stdlib.sha256",
    "site_packages_sha256": "site-packages.sha256",
    "native_sha256": "native.sha256",
}
APPLICATION_EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".rumi_snapshots",
    ".venv",
    "__pycache__",
    "node_modules",
    "python-runtime",
    "target",
    "tests",
    "user_data",
    "userdata",
    "venv",
}
APPLICATION_EXCLUDED_SUFFIXES = {".bak", ".pyc", ".pyo", ".zip"}
PYTHON_BYTECODE_ENVIRONMENT = "PYTHONDONTWRITEBYTECODE"
APPLICATION_LEGACY_AUTHORITY_FILENAMES = {
    "ecosystem.json",
    "rumi.pack.v3.json",
}
SEALED_APPLICATION_ROLE_TARGETS = (
    "app/app.py",
    "app/ecosystem/defaultspack/defaultspack/desktop_app.py",
    "app/core_runtime/host_broker/computer_host_helper.py",
)


@dataclass(frozen=True)
class TargetSpec:
    """Normalized platform information for one supported Rust target."""

    triple: str
    platform: str
    architecture: str
    windows: bool


TARGETS = {
    "aarch64-apple-darwin": TargetSpec("aarch64-apple-darwin", "macos", "arm64", False),
    "x86_64-apple-darwin": TargetSpec("x86_64-apple-darwin", "macos", "x86_64", False),
    "x86_64-unknown-linux-gnu": TargetSpec(
        "x86_64-unknown-linux-gnu", "linux", "x86_64", False
    ),
    "x86_64-pc-windows-msvc": TargetSpec(
        "x86_64-pc-windows-msvc", "windows", "x86_64", True
    ),
}

_UV_VERSION_PATTERN = re.compile(
    r"^uv "
    r"(?P<version>(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)) "
    r"\((?P<revision>[0-9a-f]{9,40}) "
    r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2}) "
    r"(?P<target>[a-z0-9_]+(?:-[a-z0-9_]+){2,4})\)$"
)


@dataclass(frozen=True)
class UvVersionIdentity:
    """Structured identity emitted by an official uv executable."""

    version: str
    revision: str
    release_date: str
    target: str


class SealedEnvironmentError(RuntimeError):
    """Raised when a sealed environment cannot be safely built or verified."""


def target_spec(target: str) -> TargetSpec:
    """Return the allowlisted target specification."""
    try:
        return TARGETS[target]
    except KeyError as exc:
        supported = ", ".join(sorted(TARGETS))
        raise SealedEnvironmentError(
            f"unsupported sealed Python target {target!r}; supported: {supported}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _posix_relative(path: Path, root: Path) -> str:
    """Return a safe POSIX relative path or fail closed."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise SealedEnvironmentError(
            f"path escapes sealed root: {path} is outside {root}"
        ) from exc
    text = relative.as_posix()
    if (
        not text
        or text.startswith("/")
        or "\\" in text
        or any(part in {"", ".", ".."} for part in text.split("/"))
    ):
        raise SealedEnvironmentError(f"unsafe sealed relative path: {text!r}")
    return text


def _is_reparse_point(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & REPARSE_POINT)


def _assert_root(root: Path) -> Path:
    """Validate and resolve a regular directory root without following links."""
    root = Path(root)
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise SealedEnvironmentError(f"sealed root is unavailable: {root}") from exc
    if (
        root.is_symlink()
        or _is_reparse_point(metadata)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise SealedEnvironmentError(f"sealed root is not a real directory: {root}")
    return root.resolve(strict=True)


def _is_sha256_identity(value: object) -> bool:
    """Return whether a value is the sealed raw SHA-256 identity."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _assert_regular_entry(path: Path, root: Path) -> os.stat_result:
    """Reject links, hardlinks, special files, and path escapes for one entry."""
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise SealedEnvironmentError(f"sealed entry disappeared: {path}") from exc
    if path.is_symlink() or _is_reparse_point(metadata):
        raise SealedEnvironmentError(
            f"sealed tree contains a link or reparse point: {path}"
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise SealedEnvironmentError(f"sealed tree contains a non-regular file: {path}")
    if metadata.st_nlink != 1:
        raise SealedEnvironmentError(f"sealed tree contains a hardlinked file: {path}")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise SealedEnvironmentError(f"sealed entry escapes its root: {path}") from exc
    return metadata


def _walk_tree(root: Path) -> Iterable[tuple[str, Path, str, os.stat_result]]:
    """Yield a deterministic, link-free directory tree inventory."""
    resolved_root = _assert_root(root)

    def visit(current: Path) -> Iterable[tuple[str, Path, str, os.stat_result]]:
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise SealedEnvironmentError(
                f"cannot read sealed directory: {current}"
            ) from exc
        for child in children:
            relative = _posix_relative(child, resolved_root)
            try:
                metadata = child.lstat()
            except OSError as exc:
                raise SealedEnvironmentError(
                    f"sealed entry disappeared: {child}"
                ) from exc
            if child.is_symlink() or _is_reparse_point(metadata):
                raise SealedEnvironmentError(
                    f"sealed tree contains a link or reparse point: {relative}"
                )
            if any(part == "__pycache__" for part in relative.split("/")) or (
                stat.S_ISREG(metadata.st_mode)
                and child.suffix.lower() in {".pyc", ".pyo"}
            ):
                raise SealedEnvironmentError(
                    f"sealed tree contains generated Python bytecode: {relative}"
                )
            if stat.S_ISDIR(metadata.st_mode):
                try:
                    child.resolve(strict=True).relative_to(resolved_root)
                except (OSError, ValueError) as exc:
                    raise SealedEnvironmentError(
                        f"sealed directory escapes its root: {relative}"
                    ) from exc
                yield relative, child, "directory", metadata
                yield from visit(child)
            elif stat.S_ISREG(metadata.st_mode):
                yield (
                    relative,
                    child,
                    "file",
                    _assert_regular_entry(child, resolved_root),
                )
            else:
                raise SealedEnvironmentError(
                    f"sealed tree contains a special file: {relative}"
                )

    yield from visit(resolved_root)


def _windows_executable(path: Path) -> bool:
    return path.suffix.lower() in {".exe", ".com", ".bat", ".cmd"}


def _executable_flag(path: Path, metadata: os.stat_result, spec: TargetSpec) -> bool:
    return bool(metadata.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)) or (
        spec.windows and _windows_executable(path)
    )


def _copy_regular_file(source: Path, destination: Path, executable: bool) -> None:
    """Copy bytes without preserving timestamps, links, or source identity."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise SealedEnvironmentError(
            f"sealed destination already exists: {destination}"
        )
    try:
        with (
            source.open("rb") as source_handle,
            destination.open("xb") as destination_handle,
        ):
            shutil.copyfileobj(source_handle, destination_handle, length=1024 * 1024)
    except OSError as exc:
        raise SealedEnvironmentError(
            f"failed to copy sealed file {source} to {destination}"
        ) from exc
    destination.chmod(0o755 if executable else 0o644)


def _copy_tree(source: Path, destination: Path, spec: TargetSpec) -> None:
    """Copy one source tree after rejecting unsafe source entries."""
    source = _assert_root(source)
    if destination.exists() or destination.is_symlink():
        raise SealedEnvironmentError(
            f"sealed destination already exists: {destination}"
        )
    destination.mkdir(parents=True)
    destination.chmod(0o755)
    for relative, source_path, kind, metadata in _walk_tree(source):
        destination_path = destination / Path(relative)
        if kind == "directory":
            destination_path.mkdir(parents=True, exist_ok=True)
            destination_path.chmod(0o755)
            continue
        _copy_regular_file(
            source_path,
            destination_path,
            _executable_flag(source_path, metadata, spec),
        )


def _copy_application_closure(
    source: Path,
    destination: Path,
    spec: TargetSpec,
) -> None:
    """Copy the tracked application closure into the sealed ``app`` root.

    Generated environments, tests, caches, and legacy authority documents are
    not importable release inputs.  Every remaining source entry is copied as
    a regular file so the sealed manifest covers the same closure that role
    wrappers execute after the core creates its private snapshot.
    """
    source = _assert_root(source)
    if destination.is_symlink() or not destination.is_dir():
        raise SealedEnvironmentError(
            f"sealed application destination is not a directory: {destination}"
        )
    for current_name, directory_names, file_names in os.walk(
        source,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_name)
        relative_current = current.relative_to(source)
        selected_directories: list[str] = []
        for name in sorted(directory_names):
            if name in APPLICATION_EXCLUDED_DIR_NAMES:
                continue
            path = current / name
            metadata = path.lstat()
            if path.is_symlink() or _is_reparse_point(metadata):
                raise SealedEnvironmentError(
                    f"sealed application closure contains a linked directory: {path}"
                )
            if not stat.S_ISDIR(metadata.st_mode):
                raise SealedEnvironmentError(
                    f"sealed application closure contains a special directory: {path}"
                )
            selected_directories.append(name)
        directory_names[:] = selected_directories

        destination_current = destination / relative_current
        destination_current.mkdir(parents=True, exist_ok=True)
        for name in sorted(file_names):
            path = current / name
            if (
                name == ".DS_Store"
                or name in APPLICATION_LEGACY_AUTHORITY_FILENAMES
                or Path(name).suffix in APPLICATION_EXCLUDED_SUFFIXES
            ):
                continue
            metadata = path.lstat()
            if path.is_symlink() or _is_reparse_point(metadata):
                raise SealedEnvironmentError(
                    f"sealed application closure contains a linked file: {path}"
                )
            if not stat.S_ISREG(metadata.st_mode):
                raise SealedEnvironmentError(
                    f"sealed application closure contains a special file: {path}"
                )
            if metadata.st_nlink != 1:
                raise SealedEnvironmentError(
                    f"sealed application closure contains a hardlink: {path}"
                )
            relative = path.relative_to(source)
            target = destination / relative
            _copy_regular_file(
                path,
                target,
                _executable_flag(path, metadata, spec),
            )


def _freeze_tree(root: Path, spec: TargetSpec) -> None:
    """Remove all write bits from the completed snapshot, including dirs."""
    root = _assert_root(root)
    entries = sorted(
        (path for path in root.rglob("*") if not path.is_symlink()),
        key=lambda path: (len(path.relative_to(root).parts), path.as_posix()),
        reverse=True,
    )
    for path in entries:
        metadata = path.lstat()
        if _is_reparse_point(metadata):
            raise SealedEnvironmentError(
                f"sealed snapshot contains a reparse point: {path}"
            )
        if stat.S_ISDIR(metadata.st_mode):
            path.chmod(IMMUTABLE_DIRECTORY_MODE)
        elif stat.S_ISREG(metadata.st_mode):
            executable = _executable_flag(path, metadata, spec)
            path.chmod(IMMUTABLE_EXECUTABLE_MODE if executable else IMMUTABLE_FILE_MODE)
        else:
            raise SealedEnvironmentError(
                f"sealed snapshot contains a special file: {path}"
            )
    root.chmod(IMMUTABLE_DIRECTORY_MODE)


def _materialize_links(
    root: Path,
    spec: TargetSpec,
    allowed_root: Path,
) -> None:
    """Materialize safe source links before copying a sealed tree."""
    root = _assert_root(root)
    allowed_root = _assert_root(allowed_root)
    links = sorted(
        (path for path in root.rglob("*") if path.is_symlink()),
        key=lambda path: (len(path.parts), path.as_posix()),
        reverse=True,
    )
    for link in links:
        try:
            target = link.resolve(strict=True)
            target.relative_to(allowed_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SealedEnvironmentError(
                f"sealed source link escapes its assembly root: {link}"
            ) from exc
        metadata = target.lstat()
        if target.is_symlink() or _is_reparse_point(metadata):
            raise SealedEnvironmentError(f"nested venv link is unsafe: {link}")
        if stat.S_ISDIR(metadata.st_mode):
            try:
                link.relative_to(target)
            except ValueError:
                pass
            else:
                raise SealedEnvironmentError(
                    f"sealed directory link would recurse into its source: {link}"
                )
            link.unlink()
            _copy_tree(target, link, spec)
        elif stat.S_ISREG(metadata.st_mode):
            if metadata.st_nlink != 1:
                raise SealedEnvironmentError(
                    f"venv link target is hardlinked: {target}"
                )
            link.unlink()
            temporary = link.with_name(f".{link.name}.{os.getpid()}.materialized")
            if temporary.exists() or temporary.is_symlink():
                raise SealedEnvironmentError(
                    f"venv materialization path already exists: {temporary}"
                )
            try:
                _copy_regular_file(
                    target,
                    temporary,
                    _executable_flag(target, metadata, spec),
                )
                os.replace(temporary, link)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            raise SealedEnvironmentError(f"venv link target is special: {target}")


def _materialize_runtime_links(root: Path, spec: TargetSpec) -> None:
    """Materialize CPython runtime aliases that stay inside the runtime root."""
    root = _assert_root(root)
    _materialize_links(root, spec, root)


def _materialize_venv_links(root: Path, spec: TargetSpec) -> None:
    """Materialize uv's venv links, including links to the sibling runtime."""
    root = _assert_root(root)
    _materialize_links(root, spec, root.parent)


def _site_packages(root: Path, python_version: str, spec: TargetSpec) -> Path:
    """Find the platform-specific venv site-packages directory."""
    minor = ".".join(python_version.split(".")[:2])
    candidates = (
        root / "Lib" / "site-packages",
        root / "lib" / f"python{minor}" / "site-packages",
    )
    for candidate in candidates:
        if candidate.is_dir() and not candidate.is_symlink():
            return candidate
    raise SealedEnvironmentError(
        f"venv site-packages directory is missing under {root} for {spec.triple}"
    )


def _runtime_python(root: Path, spec: TargetSpec) -> Path:
    path = root / "python.exe" if spec.windows else root / "bin" / "python3"
    if not path.is_file() or path.is_symlink():
        raise SealedEnvironmentError(f"native CPython executable is missing: {path}")
    return path


def _venv_python(root: Path, spec: TargetSpec) -> Path:
    path = root / "Scripts" / "python.exe" if spec.windows else root / "bin" / "python3"
    if not path.is_file() or path.is_symlink():
        raise SealedEnvironmentError(f"required venv executable is missing: {path}")
    return path


def _write_text(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(text.encode("utf-8"))
    path.chmod(mode)


def _normalize_venv(root: Path, runtime_root: Path, spec: TargetSpec) -> None:
    """Remove build-machine absolute paths from the relocatable venv."""
    cfg = root / "pyvenv.cfg"
    if not cfg.is_file() or cfg.is_symlink():
        raise SealedEnvironmentError(
            f"relocatable venv configuration is missing: {cfg}"
        )
    home = "../runtime" if spec.windows else "../runtime/bin"
    lines = cfg.read_text(encoding="utf-8").splitlines()
    replaced = False
    normalized: list[str] = []
    for line in lines:
        if line.startswith("home ="):
            normalized.append(f"home = {home}")
            replaced = True
        elif line.startswith("relocatable ="):
            normalized.append("relocatable = true")
        else:
            normalized.append(line)
    if not replaced:
        raise SealedEnvironmentError(f"venv configuration has no home entry: {cfg}")
    _write_text(cfg, "\n".join(normalized) + "\n")

    for relative, path, kind, metadata in list(_walk_tree(root)):
        if kind != "file" or not _executable_flag(path, metadata, spec):
            continue
        try:
            payload = path.read_bytes()
            text = payload.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text.startswith("#!"):
            continue
        first, separator, rest = text.partition("\n")
        if str(runtime_root) in first or str(root) in first:
            _write_text(
                path,
                "#!/usr/bin/env python3\n" + rest,
                mode=0o755,
            )


def _records(root: Path, spec: TargetSpec) -> list[dict[str, object]]:
    """Return the strict sorted file records, excluding only the manifest."""
    records: list[dict[str, object]] = []
    for relative, path, kind, metadata in _walk_tree(root):
        if kind != "file" or relative == MANIFEST_FILENAME:
            continue
        records.append(
            {
                "path": relative,
                "size": metadata.st_size,
                "sha256": _sha256_file(path),
                "executable": _executable_flag(path, metadata, spec),
            }
        )
    records.sort(key=lambda entry: str(entry["path"]))
    return records


def _files_digest(records: list[dict[str, object]]) -> str:
    """Digest the exact compact JSON bytes serialized by the core verifier."""
    payload = json.dumps(
        records,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _group_digest(records: Iterable[dict[str, object]]) -> str:
    payload = b"".join(
        f"{entry['path']}\0{entry['sha256']}\n".encode("utf-8") for entry in records
    )
    if not payload:
        raise SealedEnvironmentError("sealed sentinel group is empty")
    return _sha256_bytes(payload)


def _sentinel_groups(
    records: list[dict[str, object]],
    python_version: str,
) -> dict[str, str]:
    minor = ".".join(python_version.split(".")[:2])
    stdlib_prefixes = (
        f"runtime/lib/python{minor}/",
        f"runtime/Lib/python{minor}/",
        "runtime/Lib/",
    )
    site_prefixes = (
        f"venv/lib/python{minor}/site-packages/",
        "venv/Lib/site-packages/",
    )
    stdlib = [
        entry
        for entry in records
        if str(entry["path"]).startswith(stdlib_prefixes)
        and not str(entry["path"]).startswith("sentinels/")
    ]
    site_packages = [
        entry for entry in records if str(entry["path"]).startswith(site_prefixes)
    ]
    native_suffixes = (".so", ".dylib", ".dll", ".pyd", ".exe")
    native = [
        entry
        for entry in records
        if str(entry["path"]).lower().endswith(native_suffixes)
        or bool(entry["executable"])
    ]
    return {
        "stdlib_sha256": _group_digest(stdlib),
        "site_packages_sha256": _group_digest(site_packages),
        "native_sha256": _group_digest(native),
    }


def _expected_manifest(
    root: Path,
    spec: TargetSpec,
    python_version: str,
    release_digest: str,
) -> dict[str, object]:
    records = _records(root, spec)
    sentinels = _sentinel_groups(records, python_version)
    for name, digest in sentinels.items():
        _write_text(root / "sentinels" / SENTINEL_FILENAMES[name], digest + "\n")
    records = _records(root, spec)
    return {
        "schema": MANIFEST_SCHEMA,
        "environment_digest": _files_digest(records),
        "platform": spec.platform,
        "architecture": spec.architecture,
        "python_version": python_version,
        "package_provenance": {
            "kind": PACKAGE_KIND_BY_PLATFORM[spec.platform],
            "package_id": PACKAGE_ID,
            "release_digest": release_digest,
        },
        "sentinels": sentinels,
        "files": records,
    }


def _validate_manifest_shape(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or tuple(document) != MANIFEST_KEYS:
        raise SealedEnvironmentError(
            "sealed manifest top-level keys must be exactly " + ", ".join(MANIFEST_KEYS)
        )
    if document["schema"] != MANIFEST_SCHEMA:
        raise SealedEnvironmentError("sealed manifest schema is unsupported")
    provenance = document["package_provenance"]
    if not isinstance(provenance, dict) or tuple(provenance) != (
        "kind",
        "package_id",
        "release_digest",
    ):
        raise SealedEnvironmentError("sealed package provenance shape is invalid")
    platform = document["platform"]
    if (
        not isinstance(platform, str)
        or platform not in PACKAGE_KIND_BY_PLATFORM
        or provenance["kind"] != PACKAGE_KIND_BY_PLATFORM[platform]
        or provenance["package_id"] != PACKAGE_ID
    ):
        raise SealedEnvironmentError("sealed package provenance identity is invalid")
    sentinels = document["sentinels"]
    if not isinstance(sentinels, dict) or tuple(sentinels) != SENTINEL_KEYS:
        raise SealedEnvironmentError("sealed sentinel shape is invalid")
    digest_values = (
        *sentinels.values(),
        provenance["release_digest"],
        document["environment_digest"],
    )
    if not all(_is_sha256_identity(value) for value in digest_values):
        raise SealedEnvironmentError(
            "sealed manifest digest is not a lowercase raw SHA-256"
        )
    files = document["files"]
    if not isinstance(files, list):
        raise SealedEnvironmentError("sealed manifest files must be a list")
    for entry in files:
        if not isinstance(entry, dict) or "path" not in entry:
            raise SealedEnvironmentError("sealed file entry shape is invalid")
    for entry in files:
        if not isinstance(entry, dict) or tuple(entry) != FILE_KEYS:
            raise SealedEnvironmentError("sealed file entry shape is invalid")
        if not isinstance(entry["path"], str):
            raise SealedEnvironmentError("sealed file entry path is not text")
    if files != sorted(files, key=lambda item: item["path"]):
        raise SealedEnvironmentError("sealed manifest files must be sorted")
    for entry in files:
        path = entry["path"]
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or path == MANIFEST_FILENAME
        ):
            raise SealedEnvironmentError(f"sealed manifest path is unsafe: {path!r}")
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise SealedEnvironmentError(f"sealed manifest size is invalid: {path}")
        digest = entry["sha256"]
        if not _is_sha256_identity(digest):
            raise SealedEnvironmentError(f"sealed file digest is invalid: {path}")
        if not isinstance(entry["executable"], bool):
            raise SealedEnvironmentError(f"sealed executable flag is invalid: {path}")
    paths = [str(entry["path"]) for entry in files]
    if len(paths) != len(set(paths)):
        raise SealedEnvironmentError("sealed manifest contains duplicate paths")
    return document


def _required_paths(spec: TargetSpec) -> tuple[str, ...]:
    venv_python = "venv/Scripts/python.exe" if spec.windows else "venv/bin/python3"
    bootstrap = (
        "venv/Lib/site-packages/tobkiri_sealed/bootstrap.py"
        if spec.windows
        else "venv/lib/python3.13/site-packages/tobkiri_sealed/bootstrap.py"
    )
    return (
        LEASE_FILENAME,
        venv_python,
        bootstrap,
        "app/kernel_entry.py",
        "app/defaultspack_entry.py",
        "app/host_helper_entry.py",
        *SEALED_APPLICATION_ROLE_TARGETS,
        "sentinels/stdlib.sha256",
        "sentinels/site-packages.sha256",
        "sentinels/native.sha256",
    )


def _native_host_spec() -> TargetSpec | None:
    machine = host_platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        architecture = "x86_64"
    elif machine in {"arm64", "aarch64"}:
        architecture = "arm64" if sys.platform == "darwin" else "aarch64"
    else:
        return None
    if sys.platform == "darwin":
        return TargetSpec(
            f"{machine}-apple-darwin",
            "macos",
            architecture,
            False,
        )
    if sys.platform.startswith("linux") and architecture == "x86_64":
        return TARGETS["x86_64-unknown-linux-gnu"]
    if sys.platform == "win32" and architecture == "x86_64":
        return TARGETS["x86_64-pc-windows-msvc"]
    return None


def _free_loopback_port() -> int:
    """Reserve and release a loopback port for the Defaultspack smoke."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _run_role_smoke(
    root: Path,
    spec: TargetSpec,
    role: str,
    role_arguments: Sequence[str],
    environment: dict[str, str],
) -> None:
    """Start one real role through the parent-compatible bootstrap wire."""
    python = _venv_python(root / "venv", spec)
    environment = dict(environment)
    environment[PYTHON_BYTECODE_ENVIRONMENT] = "1"
    nonce = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(
        prefix=".sealed-python-attestation-",
        dir=root.parent,
    ) as raw_directory:
        attestation = Path(raw_directory) / f"startup-{nonce}.json"
        command = [
            os.fspath(python),
            "-I",
            "-B",
            "-m",
            "tobkiri_sealed.bootstrap",
            "--role",
            role,
            "--nonce",
            nonce,
            "--attestation",
            os.fspath(attestation),
            "--manifest",
            os.fspath(root / MANIFEST_FILENAME),
            "--environment-root",
            os.fspath(root),
            "--",
            *role_arguments,
        ]
        if role in {"typed", "defaultspack"}:
            process = subprocess.Popen(
                command,
                cwd=root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + 20
            while not attestation.exists() and process.poll() is None:
                if time.monotonic() >= deadline:
                    process.terminate()
                    process.communicate(timeout=5)
                    raise SealedEnvironmentError(
                        f"{role} role did not publish attestation before timeout"
                    )
                time.sleep(0.02)
            if not attestation.is_file() or process.poll() is not None:
                stdout, stderr = process.communicate(timeout=5)
                detail = (stderr or stdout).strip()
                raise SealedEnvironmentError(
                    f"{role} role exited before remaining live after attestation: {detail}"
                )
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
                raise SealedEnvironmentError(
                    f"{role} role did not terminate during smoke: {stderr or stdout}"
                )
        else:
            input_payload = None
            if role == "host_helper":
                input_payload = '{"function_id":"computer.observe","args":{}}\n'
            result = subprocess.run(
                command,
                cwd=root,
                env=environment,
                input=input_payload,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                raise SealedEnvironmentError(
                    f"{role} role smoke failed with {result.returncode}: {detail}"
                )
        try:
            evidence = json.loads(attestation.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SealedEnvironmentError(
                f"{role} role attestation is malformed"
            ) from exc
        if (
            tuple(evidence)
            != (
                "schema",
                "nonce",
                "role",
                "environment_digest",
                "executable",
                "prefix",
                "base_prefix",
                "sys_path",
                "stdlib_sha256",
                "site_packages_sha256",
                "native_sha256",
                "lifetime_lease",
            )
            or evidence.get("schema") != ATTESTATION_SCHEMA
            or evidence.get("nonce") != nonce
            or evidence.get("role") != role
            or evidence.get("lifetime_lease") is not True
        ):
            raise SealedEnvironmentError(f"{role} role attestation identity is invalid")


def _verify_python_smoke(root: Path, spec: TargetSpec) -> None:
    """Run relocated native imports and all three fixed roles."""
    host = _native_host_spec()
    if (
        host is None
        or host.platform != spec.platform
        or host.architecture != spec.architecture
    ):
        return
    python = _venv_python(root / "venv", spec)
    native_code = (
        "import _hashlib, _ssl, json, sys; "
        "import cryptography; "
        "print(json.dumps({'version': '.'.join(map(str, sys.version_info[:3])), "
        "'prefix': sys.prefix, 'base_prefix': sys.base_prefix}, sort_keys=True))"
    )
    environment = os.environ.copy()
    for key in list(environment):
        if key in {
            "REPO",
            "RUMI_CORE_DIR",
            "PYTHONPATH",
            "PYTHONHOME",
        } or key.startswith(("DYLD_", "LD_")):
            environment.pop(key, None)
    environment[PYTHON_BYTECODE_ENVIRONMENT] = "1"
    native_result = subprocess.run(
        [os.fspath(python), "-I", "-B", "-c", native_code],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if native_result.returncode != 0:
        detail = (native_result.stderr or native_result.stdout).strip()
        raise SealedEnvironmentError(f"relocated native import smoke failed: {detail}")
    try:
        report = json.loads(native_result.stdout)
    except json.JSONDecodeError as exc:
        raise SealedEnvironmentError("native Python smoke output is malformed") from exc
    if report.get("version") != PYTHON_VERSION:
        raise SealedEnvironmentError(
            f"native Python version mismatch: {report.get('version')!r}"
        )
    with tempfile.TemporaryDirectory(
        prefix=".sealed-python-role-state-",
        dir=root.parent,
    ) as state_directory:
        environment.update(
            {
                "RUMI_DEFAULTSPACK_OPEN_BROWSER": "0",
                "RUMI_DEFAULTSPACK_REQUIRE_OWN_BIND": "1",
                "RUMI_DEFAULTSPACK_PORT": str(_free_loopback_port()),
                "RUMI_APP_DIR": str(root / "app"),
                "RUMI_USER_DATA": state_directory,
            }
        )
        for role, role_arguments in (
            ("typed", ()),
            ("defaultspack", ()),
            ("host_helper", ()),
        ):
            _run_role_smoke(root, spec, role, role_arguments, environment)


def validate_environment(
    root: Path,
    target: str,
    *,
    expected_manifest_digest: str | None = None,
    run_native_smoke: bool = True,
) -> str:
    """Validate one sealed environment and return its raw manifest SHA-256."""
    spec = target_spec(target)
    root = _assert_root(root)
    if root.lstat().st_mode & 0o222:
        raise SealedEnvironmentError("sealed snapshot root is writable")
    manifest_path = root / MANIFEST_FILENAME
    metadata = manifest_path.lstat() if manifest_path.exists() else None
    if metadata is None or manifest_path.is_symlink() or _is_reparse_point(metadata):
        raise SealedEnvironmentError("sealed manifest is missing or linked")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise SealedEnvironmentError("sealed manifest is not an ordinary file")
    raw = manifest_path.read_bytes()
    raw_digest = _sha256_bytes(raw)
    if expected_manifest_digest and (
        not _is_sha256_identity(expected_manifest_digest)
        or raw_digest != expected_manifest_digest
    ):
        raise SealedEnvironmentError("sealed manifest raw SHA-256 binding mismatch")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SealedEnvironmentError("sealed manifest is not valid UTF-8 JSON") from exc
    document = _validate_manifest_shape(document)
    if (
        document["platform"] != spec.platform
        or document["architecture"] != spec.architecture
        or document["python_version"] != PYTHON_VERSION
    ):
        raise SealedEnvironmentError(
            "sealed manifest platform, architecture, or Python mismatch"
        )
    records = document["files"]
    actual_records = _records(root, spec)
    if records != actual_records:
        raise SealedEnvironmentError(
            "sealed file inventory does not match its manifest"
        )
    if document["environment_digest"] != _files_digest(records):
        raise SealedEnvironmentError("sealed environment digest does not match files")
    paths = {str(entry["path"]) for entry in records}
    missing = [path for path in _required_paths(spec) if path not in paths]
    if missing:
        raise SealedEnvironmentError(
            "sealed fixed entrypoint is missing: " + ", ".join(missing)
        )
    site = _site_packages(root / "venv", PYTHON_VERSION, spec)
    package_relative = _posix_relative(site / "tobkiri_sealed" / "bootstrap.py", root)
    if package_relative not in paths:
        raise SealedEnvironmentError("sealed tobkiri_sealed.bootstrap is missing")
    expected_sentinels = _sentinel_groups(records, PYTHON_VERSION)
    if document["sentinels"] != expected_sentinels:
        raise SealedEnvironmentError("sealed sentinel digest mismatch")
    for name in SENTINEL_KEYS:
        path = root / "sentinels" / SENTINEL_FILENAMES[name]
        if path.read_text(encoding="utf-8") != document["sentinels"][name] + "\n":
            raise SealedEnvironmentError(f"sealed sentinel payload mismatch: {path}")
    for _relative, path, _kind, entry_metadata in _walk_tree(root):
        if entry_metadata.st_mode & 0o222:
            raise SealedEnvironmentError(
                f"sealed snapshot entry is writable: {path.relative_to(root)}"
            )
    if run_native_smoke:
        _verify_python_smoke(root, spec)
    return raw_digest


def _load_cleanup_remove():
    path = REPOSITORY_ROOT / "tobkiri_runtime/scripts/packaging_cleanup.py"
    spec = importlib.util.spec_from_file_location("tobkiri_packaging_cleanup", path)
    if spec is None or spec.loader is None:
        raise SealedEnvironmentError(f"cannot load cleanup helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.remove_owned_path


def _remove_owned_output(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    remove_owned_path = _load_cleanup_remove()
    remove_owned_path(
        path,
        owner_root=path.parent,
        operation="replace sealed Python environment",
    )


def parse_uv_version(
    output: str,
    *,
    expected_target: str | None = None,
) -> UvVersionIdentity:
    """Parse and validate the structured official uv version identity."""
    line = output
    if line.endswith("\n"):
        line = line[:-1]
    if line.endswith("\r"):
        line = line[:-1]
    if not line or "\n" in line or "\r" in line:
        raise SealedEnvironmentError("uv --version output has unsafe line structure")
    match = _UV_VERSION_PATTERN.fullmatch(line)
    if match is None:
        raise SealedEnvironmentError(
            "uv --version output is not the expected structured official format"
        )
    identity = UvVersionIdentity(
        version=match.group("version"),
        revision=match.group("revision"),
        release_date=match.group("date"),
        target=match.group("target"),
    )
    if identity.version != UV_VERSION:
        raise SealedEnvironmentError(
            f"uv version is not pinned to {UV_VERSION}: {identity.version}"
        )
    try:
        date.fromisoformat(identity.release_date)
    except ValueError as exc:
        raise SealedEnvironmentError(
            f"uv release date is malformed: {identity.release_date}"
        ) from exc
    if identity.target not in TARGETS:
        raise SealedEnvironmentError(
            f"uv executable identity is unsupported: {identity.target}"
        )
    if expected_target is not None and identity.target != expected_target:
        raise SealedEnvironmentError(
            "uv executable identity does not match the requested target: "
            f"{identity.target} != {expected_target}"
        )
    return identity


def _uv_version(uv: Path, expected_target: str) -> UvVersionIdentity:
    try:
        result = subprocess.run(
            [os.fspath(uv), "--version"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SealedEnvironmentError(f"cannot execute pinned uv binary: {uv}") from exc
    return parse_uv_version(result.stdout or "", expected_target=expected_target)


def _validate_pinned_uv_executable(
    repo_root: Path,
    uv_path: Path | None,
    spec: TargetSpec,
) -> Path:
    """Validate the immutable uv extracted by the pinned resource preparer.

    A release build may use only the exact file staged below ``bundled``.  The
    archive and member checks happen before this function in the resource
    preparer; this second gate binds the extracted bytes and executable-reported
    target to the requested release target.  In particular, this function never
    searches ``PATH``.
    """
    bundled_root = repo_root / APP_SOURCE_ROOT / "bundled"
    expected = bundled_root / ("uv.exe" if spec.windows else "uv")
    candidate = expected if uv_path is None else Path(uv_path)
    if uv_path is not None and not candidate.is_absolute():
        raise SealedEnvironmentError("explicit pinned uv path must be absolute")
    candidate = candidate.absolute()
    authority_root = _assert_root(bundled_root if uv_path is None else candidate.parent)
    if uv_path is None:
        if candidate != expected.absolute():
            raise SealedEnvironmentError("default pinned uv path changed")
    else:
        authority_metadata = authority_root.lstat()
        if (
            candidate.name != expected.name
            or authority_root.is_symlink()
            or not stat.S_ISDIR(authority_metadata.st_mode)
            or authority_metadata.st_uid != os.geteuid()
            or authority_metadata.st_mode & 0o077
        ):
            raise SealedEnvironmentError("pinned uv authority root is not private")
    metadata = _assert_regular_entry(candidate, authority_root)
    if metadata.st_mode & 0o222:
        raise SealedEnvironmentError(
            f"pinned uv executable is owner-writable: {candidate}"
        )
    if not metadata.st_mode & 0o111:
        raise SealedEnvironmentError(
            f"pinned uv executable is not executable: {candidate}"
        )
    expected_digest = UV_BINARY_SHA256_BY_TARGET[spec.triple]
    actual_digest = _sha256_file(candidate)
    if actual_digest != expected_digest:
        raise SealedEnvironmentError(
            "pinned uv executable SHA256 mismatch for "
            f"{spec.triple}: expected {expected_digest}, got {actual_digest}"
        )
    _uv_version(candidate, spec.triple)
    return candidate


def _run_uv(
    uv: Path,
    arguments: Sequence[str | os.PathLike[str]],
    cwd: Path,
    cache: Path,
) -> None:
    environment = {
        "HOME": os.fspath(cache),
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        PYTHON_BYTECODE_ENVIRONMENT: "1",
        "TMPDIR": os.fspath(cache),
        "UV_CACHE_DIR": os.fspath(cache / "uv-cache"),
        "UV_NO_CONFIG": "1",
        "UV_NO_PROGRESS": "1",
    }
    try:
        subprocess.run(
            [os.fspath(uv), *[os.fspath(argument) for argument in arguments]],
            cwd=cwd,
            env=environment,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SealedEnvironmentError(
            f"uv sealed-environment command failed: {arguments}"
        ) from exc


def _python_archive_url(spec: TargetSpec) -> str:
    if spec.triple not in PYTHON_ARCHIVE_SHA256_BY_TARGET:
        raise SealedEnvironmentError(
            f"no pinned CPython archive authority for {spec.triple}"
        )
    name = (
        f"cpython-{PYTHON_VERSION}+{PYTHON_BUILD_REVISION}-{spec.triple}"
        "-install_only_stripped.tar.gz"
    )
    return (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        f"{PYTHON_BUILD_REVISION}/{name.replace('+', '%2B')}"
    )


def _download_pinned_python_archive(spec: TargetSpec, destination: Path) -> None:
    """Download one exact PBS archive and bind it before extraction."""
    request = urllib.request.Request(
        _python_archive_url(spec),
        headers={"User-Agent": "Tobkiri-sealed-python/1"},
    )
    digest = hashlib.sha256()
    total = 0
    with (
        urllib.request.urlopen(request, timeout=60) as response,
        destination.open("xb") as output,
    ):
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > 128 * 1024 * 1024:
                raise SealedEnvironmentError(
                    "pinned CPython archive exceeds size bound"
                )
            digest.update(chunk)
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    expected = PYTHON_ARCHIVE_SHA256_BY_TARGET[spec.triple]
    if digest.hexdigest() != expected:
        raise SealedEnvironmentError("pinned CPython archive SHA-256 mismatch")


def _unsafe_archive_member(member: tarfile.TarInfo) -> SealedEnvironmentError:
    """Return the stable rejection used for every unsafe archive member."""
    return SealedEnvironmentError(
        f"unsafe pinned CPython archive member: {member.name}"
    )


def _archive_member_parts(member: tarfile.TarInfo) -> tuple[str, ...]:
    """Return safe POSIX components for one regular archive member."""
    name = member.name
    if not isinstance(name, str):
        raise _unsafe_archive_member(member)
    if name.endswith("/"):
        if not member.isdir():
            raise _unsafe_archive_member(member)
        name = name.rstrip("/")
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or "\x00" in name
    ):
        raise _unsafe_archive_member(member)
    parts = tuple(name.split("/"))
    if (
        not parts
        or parts[0] != "python"
        or any(part in {"", ".", ".."} for part in parts)
        or any(":" in part for part in parts)
    ):
        raise _unsafe_archive_member(member)
    return parts


def _archive_member_is_excluded_bytecode(parts: tuple[str, ...]) -> bool:
    """Identify safe archive bytecode that is validated but not materialized."""
    return any(part == "__pycache__" for part in parts) or parts[-1].lower().endswith(
        (".pyc", ".pyo")
    )


def _archive_link_target(
    member: tarfile.TarInfo,
    parts: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve one archive linkname without permitting an escape."""
    linkname = member.linkname
    if (
        not isinstance(linkname, str)
        or not linkname
        or linkname.startswith("/")
        or "\\" in linkname
        or "\x00" in linkname
    ):
        raise _unsafe_archive_member(member)
    if member.islnk():
        normalized = posixpath.normpath(linkname)
    else:
        normalized = posixpath.normpath(
            posixpath.join("/".join(parts[:-1]), linkname)
        )
    if (
        normalized in {"", ".", ".."}
        or normalized.startswith("../")
        or normalized.startswith("/")
    ):
        raise SealedEnvironmentError(
            f"CPython archive link escapes: {member.name} -> {linkname}"
        )
    target_parts = tuple(normalized.split("/"))
    if (
        not target_parts
        or target_parts[0] != "python"
        or any(part in {"", ".", ".."} for part in target_parts)
        or any(":" in part for part in target_parts)
    ):
        raise SealedEnvironmentError(
            f"CPython archive link escapes: {member.name} -> {linkname}"
        )
    return target_parts


def _resolve_archive_link(
    parts: tuple[str, ...],
    names: dict[tuple[str, ...], tarfile.TarInfo],
    visiting: tuple[tuple[str, ...], ...] = (),
) -> tuple[str, ...]:
    """Resolve a validated link graph to a regular file or directory member."""
    member = names[parts]
    if member.isreg() or member.isdir():
        return parts
    if not (member.issym() or member.islnk()):
        raise _unsafe_archive_member(member)
    if parts in visiting:
        raise SealedEnvironmentError(
            f"CPython archive link cycle includes: {member.name}"
        )
    target = _archive_link_target(member, parts)
    target_member = names.get(target)
    if target_member is None:
        raise SealedEnvironmentError(
            f"CPython archive link target is missing: {member.name} -> "
            f"{'/'.join(target)}"
        )
    return _resolve_archive_link(target, names, (*visiting, parts))


def _archive_dirfd_supported() -> bool:
    """Whether this host supports descriptor-relative no-follow extraction."""
    return bool(
        hasattr(os, "O_NOFOLLOW")
        and os.open in getattr(os, "supports_dir_fd", ())
        and os.mkdir in getattr(os, "supports_dir_fd", ())
        and os.symlink in getattr(os, "supports_dir_fd", ())
    )


def _open_archive_directory(path: str | Path, *, dir_fd: int | None = None) -> int:
    """Open a real directory without following a symlink."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    if dir_fd is None:
        fd = os.open(os.fspath(path), flags)
    else:
        fd = os.open(path, flags, dir_fd=dir_fd)
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(f"archive extraction path is not a directory: {path}")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _ensure_archive_directory_fd(root_fd: int, parts: Sequence[str]) -> int:
    """Create/open a directory chain using descriptor-relative no-follow calls."""
    current_fd = os.dup(root_fd)
    try:
        for part in parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=current_fd)
            except FileExistsError:
                pass
            child_fd = _open_archive_directory(part, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = child_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _ensure_archive_directory_path(root: Path, parts: Sequence[str]) -> Path:
    """Create/open a directory chain with symlink checks for fallback hosts."""
    current = root
    for part in parts:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SealedEnvironmentError(
                f"archive extraction parent is not a real directory: {current}"
            )
    return current


def _archive_file_mode(member: tarfile.TarInfo) -> int:
    """Apply tarfile.data_filter's safe executable/read-only mode mask."""
    return member.mode & 0o755


def _write_archive_file(
    bundle: tarfile.TarFile,
    member: tarfile.TarInfo,
    fd: int,
    mode: int,
) -> None:
    """Copy one regular tar member to an already exclusively-created fd."""
    source = bundle.extractfile(member)
    if source is None:
        raise SealedEnvironmentError(
            f"regular pinned CPython archive member has no data: {member.name}"
        )
    written = 0
    try:
        with source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                view = memoryview(chunk)
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        raise OSError("archive extraction write made no progress")
                    view = view[count:]
                written += len(chunk)
        if written != member.size:
            raise SealedEnvironmentError(
                f"pinned CPython archive member size changed: {member.name}"
            )
        if hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
    finally:
        os.close(fd)


def _chmod_archive_path(path: Path, mode: int) -> None:
    """Apply a safe mode without following a final symlink."""
    try:
        os.chmod(path, mode, follow_symlinks=False)
    except TypeError:  # pragma: no cover - only old platform Python builds
        os.chmod(path, mode)


def _create_archive_symlink(
    root_fd: int | None,
    destination: Path,
    parts: tuple[str, ...],
    linkname: str,
) -> None:
    """Create one validated directory link beneath an anchored parent."""
    parent_parts = parts[:-1]
    if root_fd is not None:
        parent_fd = _ensure_archive_directory_fd(root_fd, parent_parts)
        try:
            os.symlink(linkname, parts[-1], dir_fd=parent_fd)
        except FileExistsError as error:
            raise SealedEnvironmentError(
                f"duplicate pinned CPython archive member: {'/'.join(parts)}"
            ) from error
        finally:
            os.close(parent_fd)
        return
    parent = _ensure_archive_directory_path(destination, parent_parts)
    path = parent / parts[-1]
    if os.path.lexists(path):
        raise SealedEnvironmentError(
            f"duplicate pinned CPython archive member: {'/'.join(parts)}"
        )
    try:
        os.symlink(linkname, path)
    except OSError as error:
        raise SealedEnvironmentError(
            f"failed to create pinned CPython archive link: {'/'.join(parts)}"
        ) from error


def _extract_pinned_python_archive(archive: Path, destination: Path) -> Path:
    """Extract a validated PBS tree without using unsafe tar extraction APIs."""
    use_dirfd = _archive_dirfd_supported()
    directory_modes: list[tuple[tuple[str, ...], int]] = []
    root_fd: int | None = None
    try:
        destination.mkdir(mode=0o700)
        if destination.is_symlink() or not destination.is_dir():
            raise SealedEnvironmentError(
                f"archive extraction destination is not a real directory: {destination}"
            )
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            if not members:
                raise SealedEnvironmentError("pinned CPython archive is empty")

            entries: list[tuple[tarfile.TarInfo, tuple[str, ...]]] = []
            names: dict[tuple[str, ...], tarfile.TarInfo] = {}
            folded_names: dict[tuple[str, ...], tarfile.TarInfo] = {}
            excluded_bytecode: set[tuple[str, ...]] = set()
            for member in members:
                if not (
                    member.isdir()
                    or member.isreg()
                    or member.issym()
                    or member.islnk()
                ):
                    raise _unsafe_archive_member(member)
                if member.size < 0:
                    raise _unsafe_archive_member(member)
                parts = _archive_member_parts(member)
                if _archive_member_is_excluded_bytecode(parts):
                    if not member.isreg():
                        raise SealedEnvironmentError(
                            "excluded pinned CPython bytecode member must be a "
                            f"regular file: {member.name}"
                        )
                    excluded_bytecode.add(parts)
                folded = tuple(part.casefold() for part in parts)
                if parts in names or folded in folded_names:
                    raise SealedEnvironmentError(
                        f"duplicate pinned CPython archive member: {member.name}"
                    )
                names[parts] = member
                folded_names[folded] = member
                entries.append((member, parts))

            root_member = names.get(("python",))
            if root_member is not None and not root_member.isdir():
                raise SealedEnvironmentError(
                    "pinned CPython archive must contain a python directory"
                )
            if root_member is None and not any(len(parts) > 1 for parts in names):
                raise SealedEnvironmentError(
                    "pinned CPython archive must contain a python directory"
                )
            for parts, member in names.items():
                folded_parts = tuple(part.casefold() for part in parts)
                for index in range(1, len(parts)):
                    ancestor_member = folded_names.get(folded_parts[:index])
                    if ancestor_member is not None and not ancestor_member.isdir():
                        raise SealedEnvironmentError(
                            "pinned CPython archive has a file/prefix collision: "
                            f"{member.name}"
                        )

            link_terminals: dict[tuple[str, ...], tuple[str, ...]] = {}
            for member, parts in entries:
                if member.issym() or member.islnk():
                    terminal = _resolve_archive_link(parts, names)
                    terminal_member = names[terminal]
                    if member.islnk() and not terminal_member.isreg():
                        raise SealedEnvironmentError(
                            f"pinned CPython hardlink target is not a regular file: "
                            f"{member.name}"
                        )
                    if terminal in excluded_bytecode:
                        raise SealedEnvironmentError(
                            "pinned CPython archive link targets excluded "
                            f"bytecode: {member.name}"
                        )
                    link_terminals[parts] = terminal

            if use_dirfd:
                root_fd = _open_archive_directory(destination)
                assert root_fd is not None
                python_fd = _ensure_archive_directory_fd(root_fd, ("python",))
                os.close(python_fd)
            else:
                _ensure_archive_directory_path(destination, ("python",))
            for member, parts in entries:
                if parts in excluded_bytecode:
                    continue
                if member.issym() or member.islnk():
                    continue
                if member.isdir():
                    if use_dirfd:
                        directory_fd = _ensure_archive_directory_fd(root_fd, parts)
                        os.close(directory_fd)
                    else:
                        _ensure_archive_directory_path(destination, parts)
                    directory_modes.append((parts, _archive_file_mode(member)))
                    continue

                parent_parts = parts[:-1]
                file_path: Path | None = None
                if use_dirfd:
                    parent_fd = _ensure_archive_directory_fd(root_fd, parent_parts)
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    flags |= getattr(os, "O_NOFOLLOW", 0)
                    flags |= getattr(os, "O_CLOEXEC", 0)
                    try:
                        file_fd = os.open(
                            parts[-1],
                            flags,
                            0o600,
                            dir_fd=parent_fd,
                        )
                    finally:
                        os.close(parent_fd)
                else:
                    parent = _ensure_archive_directory_path(destination, parent_parts)
                    file_path = parent / parts[-1]
                    try:
                        file_path.lstat()
                    except FileNotFoundError:
                        pass
                    else:
                        raise SealedEnvironmentError(
                            f"duplicate pinned CPython archive member: {member.name}"
                        )
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    flags |= getattr(os, "O_NOFOLLOW", 0)
                    file_fd = os.open(file_path, flags, 0o600)
                mode = _archive_file_mode(member)
                _write_archive_file(bundle, member, file_fd, mode)
                if not hasattr(os, "fchmod"):
                    _chmod_archive_path(
                        destination.joinpath(*parts) if file_path is None else file_path,
                        mode,
                    )

            for member, parts in entries:
                if parts in excluded_bytecode:
                    continue
                if not (member.issym() or member.islnk()):
                    continue
                terminal = link_terminals[parts]
                terminal_member = names[terminal]
                if terminal_member.isreg():
                    parent_parts = parts[:-1]
                    file_path: Path | None = None
                    if use_dirfd:
                        parent_fd = _ensure_archive_directory_fd(root_fd, parent_parts)
                        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                        flags |= getattr(os, "O_NOFOLLOW", 0)
                        flags |= getattr(os, "O_CLOEXEC", 0)
                        try:
                            file_fd = os.open(
                                parts[-1],
                                flags,
                                0o600,
                                dir_fd=parent_fd,
                            )
                        finally:
                            os.close(parent_fd)
                    else:
                        parent = _ensure_archive_directory_path(
                            destination, parent_parts
                        )
                        file_path = parent / parts[-1]
                        if os.path.lexists(file_path):
                            raise SealedEnvironmentError(
                                f"duplicate pinned CPython archive member: {member.name}"
                            )
                        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                        flags |= getattr(os, "O_NOFOLLOW", 0)
                        file_fd = os.open(file_path, flags, 0o600)
                    mode = _archive_file_mode(terminal_member)
                    _write_archive_file(bundle, terminal_member, file_fd, mode)
                    if not hasattr(os, "fchmod"):
                        _chmod_archive_path(
                            destination.joinpath(*parts) if file_path is None else file_path,
                            mode,
                        )
                else:
                    _create_archive_symlink(
                        root_fd,
                        destination,
                        parts,
                        member.linkname,
                    )

            for parts, mode in sorted(
                directory_modes,
                key=lambda item: len(item[0]),
                reverse=True,
            ):
                if use_dirfd:
                    directory_fd = _ensure_archive_directory_fd(root_fd, parts)
                    try:
                        os.fchmod(directory_fd, mode)
                    finally:
                        os.close(directory_fd)
                else:
                    _chmod_archive_path(destination.joinpath(*parts), mode)
    except SealedEnvironmentError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise SealedEnvironmentError(
            "pinned CPython archive extraction failed"
        ) from error
    finally:
        if root_fd is not None:
            os.close(root_fd)
    return destination / "python"


def _find_runtime(runtime: Path, spec: TargetSpec) -> Path:
    if runtime.is_symlink() or not runtime.is_dir():
        raise SealedEnvironmentError("pinned CPython runtime root is missing")
    python = _runtime_python(runtime, spec)
    code = (
        "import json,platform,sys; "
        "print(json.dumps({'version': '.'.join(map(str, sys.version_info[:3])), "
        "'machine': platform.machine().lower()}, sort_keys=True))"
    )
    environment = os.environ.copy()
    environment[PYTHON_BYTECODE_ENVIRONMENT] = "1"
    result = subprocess.run(
        [os.fspath(python), "-I", "-B", "-c", code],
        check=True,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    report = json.loads(result.stdout)
    expected_machine = (
        "amd64" if spec.windows and spec.architecture == "x86_64" else spec.architecture
    )
    if report.get("version") != PYTHON_VERSION or report.get("machine") not in {
        spec.architecture,
        expected_machine,
    }:
        raise SealedEnvironmentError(
            f"native CPython identity mismatch for {spec.triple}: {report}"
        )
    return runtime


def _write_manifest(root: Path, document: dict[str, object]) -> Path:
    path = root / MANIFEST_FILENAME
    _write_text(path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    return path


def assemble_environment(
    output_root: Path,
    runtime_source: Path,
    venv_source: Path,
    target: str,
    *,
    python_version: str = PYTHON_VERSION,
    release_digest: str,
    application_source: Path | None = None,
    sealed_source_root: Path = SEALED_SOURCE_ROOT,
) -> Path:
    """Assemble a deterministic sealed tree from prepared runtime fixtures."""
    spec = target_spec(target)
    if python_version != PYTHON_VERSION:
        raise SealedEnvironmentError(f"only CPython {PYTHON_VERSION} is supported")
    if not _is_sha256_identity(release_digest):
        raise SealedEnvironmentError("release_digest must be a lowercase raw SHA-256")
    output_root = Path(output_root)
    if output_root.exists() or output_root.is_symlink():
        raise SealedEnvironmentError(
            f"assembly destination must be empty: {output_root}"
        )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    output_root.mkdir()
    output_root.chmod(0o755)
    _materialize_runtime_links(Path(runtime_source), spec)
    _copy_tree(Path(runtime_source), output_root / "runtime", spec)
    _materialize_venv_links(Path(venv_source), spec)
    _normalize_venv(Path(venv_source), Path(runtime_source), spec)
    _copy_tree(Path(venv_source), output_root / "venv", spec)
    _copy_tree(sealed_source_root / "app", output_root / "app", spec)
    if application_source is not None:
        _copy_application_closure(
            Path(application_source),
            output_root / "app",
            spec,
        )
    site_packages = _site_packages(output_root / "venv", python_version, spec)
    _copy_tree(
        sealed_source_root / "tobkiri_sealed",
        site_packages / "tobkiri_sealed",
        spec,
    )
    sentinels = output_root / "sentinels"
    sentinels.mkdir()
    sentinels.chmod(0o755)
    _write_text(output_root / LEASE_FILENAME, LEASE_CONTENT)
    document = _expected_manifest(output_root, spec, python_version, release_digest)
    manifest_path = _write_manifest(output_root, document)
    _freeze_tree(output_root, spec)
    validate_environment(output_root, target, run_native_smoke=False)
    return manifest_path


def _copy_verified_source_snapshot(
    source_root: Path,
    destination: Path,
    expected_manifest_digest: str,
    expected_release_digest: str,
) -> Path:
    """Copy exactly the digest-bound committed snapshot through opened files."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_digest):
        raise SealedEnvironmentError("source inventory digest must be raw SHA-256")
    manifest_path = source_root / SOURCE_SNAPSHOT_MANIFEST
    descriptor = os.open(manifest_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        encoded = b""
        while chunk := os.read(descriptor, 1024 * 1024):
            encoded += chunk
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o222
        or (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or hashlib.sha256(encoded).hexdigest() != expected_manifest_digest
    ):
        raise SealedEnvironmentError("committed source inventory authority changed")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise SealedEnvironmentError(f"duplicate source inventory field: {key}")
            result[key] = value
        return result

    try:
        document = json.loads(encoded, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SealedEnvironmentError("invalid committed source inventory") from exc
    if (
        not isinstance(document, dict)
        or set(document)
        != {"schema", "source_commit", "source_tree", "source_manifest_sha256", "files"}
        or document.get("schema") != SOURCE_SNAPSHOT_SCHEMA
        or not re.fullmatch(r"[0-9a-f]{40}", str(document.get("source_commit", "")))
        or not re.fullmatch(r"[0-9a-f]{40}", str(document.get("source_tree", "")))
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(document.get("source_manifest_sha256", ""))
        )
        or not isinstance(document.get("files"), list)
    ):
        raise SealedEnvironmentError("committed source inventory schema mismatch")
    release_frame = {
        "schema": SOURCE_SNAPSHOT_SCHEMA,
        "source_commit": document["source_commit"],
        "source_tree": document["source_tree"],
        "source_manifest_sha256": document["source_manifest_sha256"],
        "source_inventory_sha256": expected_manifest_digest,
    }
    release_bytes = (
        json.dumps(release_frame, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_release_digest)
        or hashlib.sha256(release_bytes).hexdigest() != expected_release_digest
    ):
        raise SealedEnvironmentError("committed source release domain mismatch")
    entries = document["files"]
    expected_paths: list[str] = []
    destination.mkdir(mode=0o700)
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "size",
            "sha256",
            "executable",
        }:
            raise SealedEnvironmentError("committed source entry schema mismatch")
        relative = entry["path"]
        if (
            not isinstance(relative, str)
            or relative.startswith("/")
            or any(part in {"", ".", ".."} for part in Path(relative).parts)
            or not isinstance(entry["size"], int)
            or entry["size"] < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(entry["sha256"]))
            or not isinstance(entry["executable"], bool)
            or (expected_paths and relative <= expected_paths[-1])
        ):
            raise SealedEnvironmentError("committed source entry is unsafe or unsorted")
        source = source_root.joinpath(*Path(relative).parts)
        source_descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(source_descriptor)
            payload = b""
            while chunk := os.read(source_descriptor, 1024 * 1024):
                payload += chunk
            closed = os.fstat(source_descriptor)
        finally:
            os.close(source_descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_mode & 0o222
            or bool(opened.st_mode & 0o111) != entry["executable"]
            or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            != (closed.st_dev, closed.st_ino, closed.st_size, closed.st_mtime_ns)
            or len(payload) != entry["size"]
            or hashlib.sha256(payload).hexdigest() != entry["sha256"]
        ):
            raise SealedEnvironmentError(f"committed source bytes changed: {relative}")
        target = destination.joinpath(*Path(relative).parts)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target_descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o500 if entry["executable"] else 0o400,
        )
        try:
            offset = 0
            while offset < len(payload):
                offset += os.write(target_descriptor, payload[offset:])
            os.fsync(target_descriptor)
            os.fchmod(target_descriptor, 0o500 if entry["executable"] else 0o400)
        finally:
            os.close(target_descriptor)
        expected_paths.append(relative)
    # Git tree order compares the slash separator with the next path byte,
    # while the filesystem walk sorts each path component independently.
    # Normalize only the order comparison; every entry was already verified
    # for exact bytes, mode, link safety, and digest above.
    expected_paths.sort(key=lambda relative: tuple(relative.split("/")))
    actual = []
    for relative, _path, kind, _metadata in _walk_tree(source_root):
        if relative == SOURCE_SNAPSHOT_MANIFEST:
            continue
        if kind == "directory":
            continue
        if kind != "file":
            raise SealedEnvironmentError("committed source snapshot contains a link")
        actual.append(relative)
    if actual != expected_paths:
        raise SealedEnvironmentError(
            "committed source inventory has missing or extra files"
        )
    manifest_entry = next(
        (
            entry
            for entry in entries
            if entry["path"]
            == "tobkiri_runtime/packaged_defaultspack_source_manifest.v1.json"
        ),
        None,
    )
    if (
        manifest_entry is None
        or manifest_entry["sha256"] != document["source_manifest_sha256"]
    ):
        raise SealedEnvironmentError("runtime source manifest authority mismatch")
    return destination


def build_environment(
    repo_root: Path,
    target: str,
    *,
    output_root: Path | None = None,
    requirements_path: Path | None = None,
    uv_path: Path | None = None,
    release_digest: str | None = None,
    source_inventory_sha256: str | None = None,
) -> Path:
    """Build a native release environment with pinned uv and hash locks."""
    spec = target_spec(target)
    repo_root = Path(repo_root).resolve(strict=True)
    output_root = Path(output_root or repo_root / DEFAULT_OUTPUT_RELATIVE)
    if requirements_path is not None:
        raise SealedEnvironmentError(
            "formal build does not accept an external requirements path"
        )
    uv = _validate_pinned_uv_executable(repo_root, uv_path, spec)
    if not release_digest:
        raise SealedEnvironmentError("formal source release digest is required")
    source_parent = output_root.parent
    source_parent.mkdir(parents=True, exist_ok=True)
    _remove_owned_output(output_root)
    with tempfile.TemporaryDirectory(
        prefix=".sealed-python-build-", dir=source_parent
    ) as raw:
        work = Path(raw)
        verified_source = _copy_verified_source_snapshot(
            repo_root,
            work / "source",
            source_inventory_sha256 or "",
            release_digest or "",
        )
        requirements_path = verified_source / DEFAULT_REQUIREMENTS_RELATIVE
        cache = work / "cache"
        cache.mkdir(mode=0o700)
        archive = work / "python.tar.gz"
        _download_pinned_python_archive(spec, archive)
        runtime_source = _find_runtime(
            _extract_pinned_python_archive(archive, work / "python-install"), spec
        )
        runtime_copy = work / "runtime"
        _materialize_runtime_links(runtime_source, spec)
        _copy_tree(runtime_source, runtime_copy, spec)
        runtime_python = _runtime_python(runtime_copy, spec)
        venv_source = work / "venv"
        _run_uv(
            uv,
            [
                "venv",
                venv_source,
                "--python",
                runtime_python,
                "--relocatable",
                "--link-mode",
                "copy",
                "--no-project",
            ],
            verified_source,
            cache,
        )
        _run_uv(
            uv,
            [
                "pip",
                "sync",
                "--python",
                _venv_python(venv_source, spec),
                "--require-hashes",
                "--only-binary",
                ":all:",
                "--link-mode",
                "copy",
                "--python-platform",
                target,
                requirements_path,
            ],
            verified_source,
            cache,
        )
        assembled = work / "python-runtime"
        assemble_environment(
            assembled,
            runtime_copy,
            venv_source,
            target,
            release_digest=release_digest,
            application_source=verified_source / APP_SOURCE_ROOT,
            sealed_source_root=(
                verified_source / ".github/scripts/sealed_python_sources"
            ),
        )
        validate_environment(assembled, target, run_native_smoke=False)
        shutil.move(os.fspath(assembled), os.fspath(output_root))
    manifest = output_root / MANIFEST_FILENAME
    digest = validate_environment(output_root, target, run_native_smoke=True)
    print(f"{MANIFEST_SHA_ENV}={digest}")
    return manifest


def _write_binding(path: Path, digest: str) -> None:
    """Write a shell-neutral environment binding outside the sealed root."""
    _write_text(path, f"{MANIFEST_SHA_ENV}={digest}\n")


def _write_packaging_binding(
    path: Path,
    root: Path,
    digest: str,
    spec: TargetSpec,
    source_snapshot: Path,
    source_tree: str,
    source_inventory_sha256: str,
    release_digest: str,
) -> None:
    """Create the private, single-writer GitHub environment binding."""
    python = _venv_python(root / "venv", spec)
    if (
        not source_snapshot.is_absolute()
        or source_snapshot.is_symlink()
        or not source_snapshot.is_dir()
        or stat.S_IMODE(source_snapshot.stat().st_mode) != 0o500
        or not re.fullmatch(r"[0-9a-f]{40}", source_tree)
        or not re.fullmatch(r"[0-9a-f]{64}", source_inventory_sha256)
        or not re.fullmatch(r"[0-9a-f]{64}", release_digest)
    ):
        raise SealedEnvironmentError("invalid committed source snapshot binding")
    payload = (
        f"{MANIFEST_SHA_ENV}={digest}\n"
        f"TOBKIRI_PACKAGING_PYTHON={python}\n"
        f"TOBKIRI_PACKAGING_PYTHON_SHA256={_sha256_file(python)}\n"
        f"TOBKIRI_PACKAGING_PYTHON_SNAPSHOT={root}\n"
        f"TOBKIRI_PACKAGING_PYTHON_INVENTORY_SHA256={digest}\n"
        f"TOBKIRI_PACKAGING_SOURCE_SNAPSHOT={source_snapshot}\n"
        f"TOBKIRI_PACKAGING_SOURCE_TREE={source_tree}\n"
        f"TOBKIRI_PACKAGING_SOURCE_INVENTORY_SHA256={source_inventory_sha256}\n"
        f"TOBKIRI_PACKAGING_RELEASE_DIGEST={release_digest}\n"
    )
    if "\r" in payload or any(line.count("=") != 1 for line in payload.splitlines()):
        raise SealedEnvironmentError("unsafe packaging environment payload")
    parent = path.parent.resolve(strict=True)
    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp is not None:
        try:
            parent.relative_to(Path(runner_temp).resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise SealedEnvironmentError(
                "packaging environment output escapes RUNNER_TEMP"
            ) from exc
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    opened = os.fstat(descriptor)
    try:
        encoded = payload.encode("utf-8")
        offset = 0
        while offset < len(encoded):
            offset += os.write(descriptor, encoded[offset:])
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        named = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o077
            or (metadata.st_dev, metadata.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise SealedEnvironmentError(
                "packaging environment output identity changed"
            )
    except Exception:
        try:
            named = path.lstat()
            if (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino):
                path.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(descriptor)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the build/check command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--target", required=True, choices=tuple(sorted(TARGETS)))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--uv-path", type=Path)
    parser.add_argument("--release-digest")
    parser.add_argument("--source-tree")
    parser.add_argument("--source-inventory-sha256")
    parser.add_argument("--env-output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build or verify the fixed sealed Python environment."""
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    output_root = Path(args.output_root or repo_root / DEFAULT_OUTPUT_RELATIVE)
    try:
        if args.cleanup:
            if args.check or args.env_output is not None:
                raise SealedEnvironmentError("--cleanup is an exclusive action")
            expected = os.environ.get(MANIFEST_SHA_ENV)
            validate_environment(
                output_root,
                args.target,
                expected_manifest_digest=expected,
                run_native_smoke=False,
            )
            descriptor = os.open(
                output_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                before = os.fstat(descriptor)
                named = output_root.lstat()
                if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
                    raise SealedEnvironmentError("cleanup snapshot identity changed")

                def unseal_directories(directory: int, device: int) -> None:
                    os.fchmod(directory, 0o700)
                    for name in os.listdir(directory):
                        metadata = os.stat(
                            name, dir_fd=directory, follow_symlinks=False
                        )
                        if metadata.st_dev != device:
                            raise SealedEnvironmentError("mount in cleanup snapshot")
                        if stat.S_ISDIR(metadata.st_mode):
                            child = os.open(
                                name,
                                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory,
                            )
                            try:
                                unseal_directories(child, device)
                            finally:
                                os.close(child)

                unseal_directories(descriptor, before.st_dev)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            _remove_owned_output(output_root)
            return 0
        if args.check:
            digest = validate_environment(
                output_root,
                args.target,
                expected_manifest_digest=os.environ.get(MANIFEST_SHA_ENV),
                run_native_smoke=True,
            )
            print(f"{MANIFEST_SHA_ENV}={digest}")
        else:
            manifest = build_environment(
                repo_root,
                args.target,
                output_root=output_root,
                requirements_path=args.requirements,
                uv_path=args.uv_path,
                release_digest=args.release_digest,
                source_inventory_sha256=args.source_inventory_sha256,
            )
            digest = _sha256_file(manifest)
        if args.env_output:
            _write_packaging_binding(
                args.env_output,
                output_root,
                digest,
                target_spec(args.target),
                repo_root,
                args.source_tree or "",
                args.source_inventory_sha256 or "",
                args.release_digest or "",
            )
        return 0
    except (OSError, SealedEnvironmentError, subprocess.CalledProcessError) as exc:
        print(f"sealed Python environment preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
