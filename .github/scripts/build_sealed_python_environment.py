#!/usr/bin/env python3
"""Build and verify Tobkiri's fixed-layout sealed Python environment.

The release build runs on the native CI runner for one supported target.  It
uses the repository's pinned ``uv`` binary, the exact CPython patch version,
and the hash-locked runtime requirements export.  The resulting tree is
copied into ``tobkiri_runtime/python-runtime`` and later assembled by the
Tauri resource preparer under ``{resource_dir}/app``.

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
import platform as host_platform
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
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
MANIFEST_SCHEMA = "io.tobkiri.sealed-python-environment.v1"
ATTESTATION_SCHEMA = "io.tobkiri.sealed-python-attestation.v1"
MANIFEST_SHA_ENV = "TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256"
LEASE_FILENAME = "lease.v1"
LEASE_CONTENT = "io.tobkiri.sealed-python-lease.v1\n"
UV_VERSION = "0.11.14"
PYTHON_VERSION = "3.13.13"
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
PACKAGE_KIND_BY_PLATFORM = {
    "macos": "apple-code-signature-v1",
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
    "aarch64-apple-darwin": TargetSpec(
        "aarch64-apple-darwin", "macos", "arm64", False
    ),
    "x86_64-apple-darwin": TargetSpec(
        "x86_64-apple-darwin", "macos", "x86_64", False
    ),
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
    if root.is_symlink() or _is_reparse_point(metadata) or not stat.S_ISDIR(metadata.st_mode):
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
        raise SealedEnvironmentError(f"sealed tree contains a link or reparse point: {path}")
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
            raise SealedEnvironmentError(f"cannot read sealed directory: {current}") from exc
        for child in children:
            relative = _posix_relative(child, resolved_root)
            try:
                metadata = child.lstat()
            except OSError as exc:
                raise SealedEnvironmentError(f"sealed entry disappeared: {child}") from exc
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
                yield relative, child, "file", _assert_regular_entry(child, resolved_root)
            else:
                raise SealedEnvironmentError(f"sealed tree contains a special file: {relative}")

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
        raise SealedEnvironmentError(f"sealed destination already exists: {destination}")
    try:
        with source.open("rb") as source_handle, destination.open("xb") as destination_handle:
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
        raise SealedEnvironmentError(f"sealed destination already exists: {destination}")
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
            raise SealedEnvironmentError(f"sealed snapshot contains a reparse point: {path}")
        if stat.S_ISDIR(metadata.st_mode):
            path.chmod(IMMUTABLE_DIRECTORY_MODE)
        elif stat.S_ISREG(metadata.st_mode):
            executable = _executable_flag(path, metadata, spec)
            path.chmod(
                IMMUTABLE_EXECUTABLE_MODE if executable else IMMUTABLE_FILE_MODE
            )
        else:
            raise SealedEnvironmentError(f"sealed snapshot contains a special file: {path}")
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
                raise SealedEnvironmentError(f"venv link target is hardlinked: {target}")
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
        raise SealedEnvironmentError(f"relocatable venv configuration is missing: {cfg}")
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
        f"{entry['path']}\0{entry['sha256']}\n".encode("utf-8")
        for entry in records
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
        entry
        for entry in records
        if str(entry["path"]).startswith(site_prefixes)
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
    if host is None or host.platform != spec.platform or host.architecture != spec.architecture:
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
        if key in {"REPO", "RUMI_CORE_DIR", "PYTHONPATH", "PYTHONHOME"} or key.startswith(
            ("DYLD_", "LD_")
        ):
            environment.pop(key, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
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
        raise SealedEnvironmentError("sealed manifest platform, architecture, or Python mismatch")
    records = document["files"]
    actual_records = _records(root, spec)
    if records != actual_records:
        raise SealedEnvironmentError("sealed file inventory does not match its manifest")
    if document["environment_digest"] != _files_digest(records):
        raise SealedEnvironmentError("sealed environment digest does not match files")
    paths = {str(entry["path"]) for entry in records}
    missing = [path for path in _required_paths(spec) if path not in paths]
    if missing:
        raise SealedEnvironmentError("sealed fixed entrypoint is missing: " + ", ".join(missing))
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


def _source_digest(repo_root: Path) -> str:
    """Create a deterministic release identity from source and lock inputs."""
    entries: list[tuple[str, str]] = []
    runtime_root = repo_root / APP_SOURCE_ROOT
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "--", APP_SOURCE_ROOT],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout.decode("utf-8").split("\0")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SealedEnvironmentError("cannot enumerate tracked Tobkiri runtime sources") from exc
    for relative in tracked:
        if not relative or relative.startswith(f"{APP_SOURCE_ROOT}/python-runtime/"):
            continue
        source = repo_root / relative
        if source.is_symlink() or not source.is_file():
            raise SealedEnvironmentError(f"source identity input is unsafe: {relative}")
        entries.append((relative, _sha256_file(source)))
    for relative, source in _source_files(SEALED_SOURCE_ROOT):
        entries.append((f".github/scripts/sealed_python_sources/{relative}", _sha256_file(source)))
    del runtime_root
    entries.sort()
    payload = b"".join(f"{path}\0{digest}\n".encode("utf-8") for path, digest in entries)
    return _sha256_bytes(payload)


def _source_files(root: Path) -> Iterable[tuple[str, Path]]:
    """Yield regular source files below a packaging template root."""
    for relative, path, kind, _metadata in _walk_tree(root):
        if kind == "file":
            yield relative, path


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
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    candidate = candidate.absolute()
    if candidate != expected.absolute():
        raise SealedEnvironmentError(
            "pinned uv executable must be the archive-extracted resource at "
            f"{expected}"
        )
    metadata = _assert_regular_entry(candidate, bundled_root)
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


def _run_uv(uv: Path, arguments: Sequence[str | os.PathLike[str]], cwd: Path) -> None:
    environment = os.environ.copy()
    environment["UV_NO_CONFIG"] = "1"
    environment["UV_NO_PROGRESS"] = "1"
    try:
        subprocess.run(
            [os.fspath(uv), *[os.fspath(argument) for argument in arguments]],
            cwd=cwd,
            env=environment,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SealedEnvironmentError(f"uv sealed-environment command failed: {arguments}") from exc


def _find_runtime(install_root: Path, spec: TargetSpec) -> Path:
    candidates = sorted(
        path
        for path in install_root.iterdir()
        if path.is_dir() and path.name.startswith(f"cpython-{PYTHON_VERSION}-")
    )
    if len(candidates) != 1:
        raise SealedEnvironmentError(
            f"uv installed an unexpected CPython layout: {[path.name for path in candidates]}"
        )
    runtime = candidates[0]
    python = _runtime_python(runtime, spec)
    code = (
        "import json,platform,sys; "
        "print(json.dumps({'version': '.'.join(map(str, sys.version_info[:3])), "
        "'machine': platform.machine().lower()}, sort_keys=True))"
    )
    result = subprocess.run(
        [os.fspath(python), "-I", "-B", "-c", code],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    report = json.loads(result.stdout)
    expected_machine = "amd64" if spec.windows and spec.architecture == "x86_64" else spec.architecture
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
) -> Path:
    """Assemble a deterministic sealed tree from prepared runtime fixtures."""
    spec = target_spec(target)
    if python_version != PYTHON_VERSION:
        raise SealedEnvironmentError(f"only CPython {PYTHON_VERSION} is supported")
    if not _is_sha256_identity(release_digest):
        raise SealedEnvironmentError(
            "release_digest must be a lowercase raw SHA-256"
        )
    output_root = Path(output_root)
    if output_root.exists() or output_root.is_symlink():
        raise SealedEnvironmentError(f"assembly destination must be empty: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    output_root.mkdir()
    output_root.chmod(0o755)
    _materialize_runtime_links(Path(runtime_source), spec)
    _copy_tree(Path(runtime_source), output_root / "runtime", spec)
    _materialize_venv_links(Path(venv_source), spec)
    _normalize_venv(Path(venv_source), Path(runtime_source), spec)
    _copy_tree(Path(venv_source), output_root / "venv", spec)
    _copy_tree(SEALED_SOURCE_ROOT / "app", output_root / "app", spec)
    if application_source is not None:
        _copy_application_closure(
            Path(application_source),
            output_root / "app",
            spec,
        )
    site_packages = _site_packages(output_root / "venv", python_version, spec)
    _copy_tree(
        SEALED_SOURCE_ROOT / "tobkiri_sealed",
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


def build_environment(
    repo_root: Path,
    target: str,
    *,
    output_root: Path | None = None,
    requirements_path: Path | None = None,
    uv_path: Path | None = None,
    release_digest: str | None = None,
) -> Path:
    """Build a native release environment with pinned uv and hash locks."""
    spec = target_spec(target)
    repo_root = Path(repo_root).resolve(strict=True)
    output_root = Path(output_root or repo_root / DEFAULT_OUTPUT_RELATIVE)
    requirements_path = Path(
        requirements_path or repo_root / DEFAULT_REQUIREMENTS_RELATIVE
    )
    if requirements_path.is_symlink() or not requirements_path.is_file():
        raise SealedEnvironmentError(f"locked runtime requirements are missing: {requirements_path}")
    uv = _validate_pinned_uv_executable(repo_root, uv_path, spec)
    release_digest = release_digest or _source_digest(repo_root)
    source_parent = output_root.parent
    source_parent.mkdir(parents=True, exist_ok=True)
    _remove_owned_output(output_root)
    with tempfile.TemporaryDirectory(prefix=".sealed-python-build-", dir=source_parent) as raw:
        work = Path(raw)
        install_root = work / "python-install"
        _run_uv(
            uv,
            [
                "python",
                "install",
                PYTHON_VERSION,
                "--install-dir",
                install_root,
                "--no-bin",
            ],
            repo_root,
        )
        runtime_source = _find_runtime(install_root, spec)
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
            repo_root,
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
            repo_root,
        )
        assembled = work / "python-runtime"
        assemble_environment(
            assembled,
            runtime_copy,
            venv_source,
            target,
            release_digest=release_digest,
            application_source=repo_root / APP_SOURCE_ROOT,
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the build/check command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--target", required=True, choices=tuple(sorted(TARGETS)))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--uv-path", type=Path)
    parser.add_argument("--release-digest")
    parser.add_argument("--env-output", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build or verify the fixed sealed Python environment."""
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    output_root = Path(args.output_root or repo_root / DEFAULT_OUTPUT_RELATIVE)
    try:
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
            )
            digest = _sha256_file(manifest)
        if args.env_output:
            _write_binding(args.env_output, digest)
        return 0
    except (OSError, SealedEnvironmentError, subprocess.CalledProcessError) as exc:
        print(f"sealed Python environment preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
