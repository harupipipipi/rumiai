"""Verified ``python -I -B -m tobkiri_sealed.bootstrap`` process boundary.

The Launcher supplies the role, nonce, manifest, environment root, and the
attestation destination.  Bootstrap never invents an identity or accepts
unknown bootstrap arguments; everything after ``--`` is passed to the fixed
role without interpretation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

from . import SCHEMA

PROTOCOL_SCHEMA = "io.tobkiri.sealed-python-launch.v1"
ATTESTATION_SCHEMA = "io.tobkiri.sealed-python-attestation.v1"
ROLE_ENTRYPOINTS = {
    "typed": "kernel_entry.py",
    "defaultspack": "defaultspack_entry.py",
    "host_helper": "host_helper_entry.py",
}
ROLE_TARGETS = {
    "typed": ("app.py",),
    "defaultspack": (
        "ecosystem",
        "defaultspack",
        "defaultspack",
        "desktop_app.py",
    ),
    "host_helper": (
        "core_runtime",
        "host_broker",
        "computer_host_helper.py",
    ),
}
MANIFEST_NAME = "sealed-environment.v1.json"
MANIFEST_SHA_ENV = "TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256"
LEASE_NAME = "lease.v1"
REPARSE_POINT = 0x0400
FILE_KEYS = ("path", "size", "sha256", "executable")
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
SENTINEL_KEYS = (
    "stdlib_sha256",
    "site_packages_sha256",
    "native_sha256",
)
SENTINEL_FILENAMES = {
    "stdlib_sha256": "stdlib.sha256",
    "site_packages_sha256": "site-packages.sha256",
    "native_sha256": "native.sha256",
}
PACKAGE_KIND_BY_PLATFORM = {
    "macos": "apple-code-signature-v1",
    "linux": "linux-immutable-package-v1",
    "windows": "windows-authenticode-v1",
}
FORBIDDEN_LAUNCH_ENVIRONMENTS = {
    "REPO",
    "RUMI_CORE_DIR",
    "PYTHONPATH",
    "PYTHONHOME",
}


class SealedBootstrapError(RuntimeError):
    """Raised when the supplied sealed process contract is unsafe."""


_SCOPE_CONSTRUCTOR_TOKEN = object()


class _SealedDispatchScope:
    """Opaque bootstrap-issued capability for one sealed role target.

    The capability is created only after the supplied manifest has been read
    and is passed through the fixed wrapper API. Packaged application code
    must prove that its own module file is the exact manifest-bound target;
    no basename or environment variable can opt it into the sealed path.
    """

    __slots__ = (
        "_constructor_token",
        "_root",
        "_manifest_path",
        "_manifest_digest",
        "_environment_digest",
        "_target",
    )

    def __init__(
        self,
        constructor_token: object,
        root: Path,
        manifest_path: Path,
        manifest_digest: str,
        environment_digest: str,
        target: Sequence[str],
    ) -> None:
        if constructor_token is not _SCOPE_CONSTRUCTOR_TOKEN:
            raise TypeError("sealed dispatch scope is bootstrap-private")
        if not _is_sha256_identity(manifest_digest) or not _is_sha256_identity(
            environment_digest
        ):
            raise SealedBootstrapError("sealed dispatch scope identity is invalid")
        self._constructor_token = constructor_token
        self._root = root
        self._manifest_path = manifest_path
        self._manifest_digest = manifest_digest
        self._environment_digest = environment_digest
        self._target = tuple(target)

    def app_root_for(self, module_file: str | os.PathLike[str]) -> Path:
        """Return the app root only for this scope's exact sealed target."""
        if self._constructor_token is not _SCOPE_CONSTRUCTOR_TOKEN:
            raise SealedBootstrapError("sealed dispatch scope token changed")
        expected_manifest = self._root / MANIFEST_NAME
        if self._manifest_path != expected_manifest:
            raise SealedBootstrapError("sealed dispatch scope manifest is not bound")
        try:
            if _sha256_bytes(self._manifest_path.read_bytes()) != self._manifest_digest:
                raise SealedBootstrapError("sealed dispatch scope manifest changed")
            app_root = _assert_real_directory(self._root / "app", "sealed application root")
            candidate = Path(module_file)
            expected = app_root.joinpath(*self._target)
            candidate_resolved = candidate.resolve(strict=True)
            expected_resolved = expected.resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SealedBootstrapError("sealed dispatch target is unavailable") from exc
        if (
            not candidate.is_absolute()
            or candidate != candidate_resolved
            or candidate_resolved != expected_resolved
        ):
            raise SealedBootstrapError(
                "sealed dispatch target is not the manifest-bound application file"
            )
        _assert_regular_file(expected, "sealed dispatch target")
        return app_root


def _sha256_bytes(payload: bytes) -> str:
    """Return the sealed raw SHA-256 identity."""
    return hashlib.sha256(payload).hexdigest()


def _is_sha256_identity(value: object) -> bool:
    """Return whether a value is a lowercase raw 64-hex identity."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_reparse_point(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & REPARSE_POINT)


def _assert_real_directory(
    path: Path,
    label: str,
    *,
    require_immutable: bool = True,
) -> Path:
    """Require a canonical, non-linked directory."""
    if not path.is_absolute():
        raise SealedBootstrapError(f"{label} must be absolute")
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SealedBootstrapError(f"{label} is unavailable: {path}") from exc
    if (
        path != resolved
        or path.is_symlink()
        or _is_reparse_point(metadata)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise SealedBootstrapError(f"{label} is linked or not a directory: {path}")
    if require_immutable and metadata.st_mode & 0o222:
        raise SealedBootstrapError(f"{label} is writable: {path}")
    return resolved


def _assert_regular_file(
    path: Path,
    label: str,
    *,
    allow_missing: bool = False,
    require_immutable: bool = True,
) -> Path:
    """Require a canonical regular file with one link and no write bits."""
    if not path.is_absolute():
        raise SealedBootstrapError(f"{label} must be absolute")
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        if allow_missing:
            return path
        raise SealedBootstrapError(f"{label} is missing: {path}")
    except (OSError, RuntimeError) as exc:
        raise SealedBootstrapError(f"{label} is unavailable: {path}") from exc
    if (
        path != resolved
        or path.is_symlink()
        or _is_reparse_point(metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or (require_immutable and metadata.st_mode & 0o222)
    ):
        raise SealedBootstrapError(f"{label} is linked, writable, or not regular: {path}")
    return resolved


def _safe_inventory_path(root: Path, relative: str) -> Path:
    """Resolve a manifest path without accepting links or path escapes."""
    if (
        not relative
        or relative.startswith("/")
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise SealedBootstrapError(f"sealed inventory path is unsafe: {relative!r}")
    path = root.joinpath(*relative.split("/"))
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SealedBootstrapError(f"sealed inventory path is unavailable: {relative}") from exc
    if (
        path != resolved
        or path.is_symlink()
        or _is_reparse_point(metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o222
    ):
        raise SealedBootstrapError(f"sealed inventory path is unsafe: {relative}")
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SealedBootstrapError(f"sealed inventory path escapes root: {relative}") from exc
    return path


def _validate_manifest_shape(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or tuple(document) != MANIFEST_KEYS:
        raise SealedBootstrapError("sealed manifest top-level shape is invalid")
    if document["schema"] != SCHEMA:
        raise SealedBootstrapError("sealed manifest schema is unsupported")
    platform_name = document["platform"]
    if platform_name not in PACKAGE_KIND_BY_PLATFORM:
        raise SealedBootstrapError("sealed platform identity is invalid")
    if document["architecture"] not in {"arm64", "aarch64", "x86_64"}:
        raise SealedBootstrapError("sealed architecture identity is invalid")
    if document["python_version"] != "3.13.13":
        raise SealedBootstrapError("sealed Python version is unsupported")
    provenance = document["package_provenance"]
    if not isinstance(provenance, dict) or tuple(provenance) != (
        "kind",
        "package_id",
        "release_digest",
    ):
        raise SealedBootstrapError("sealed package provenance shape is invalid")
    if (
        provenance["kind"] != PACKAGE_KIND_BY_PLATFORM[platform_name]
        or provenance["package_id"] != "dev.tobkiri.launcher"
        or not _is_sha256_identity(provenance["release_digest"])
    ):
        raise SealedBootstrapError("sealed package provenance identity is invalid")
    sentinels = document["sentinels"]
    if not isinstance(sentinels, dict) or tuple(sentinels) != SENTINEL_KEYS:
        raise SealedBootstrapError("sealed sentinel shape is invalid")
    if not all(_is_sha256_identity(sentinels[key]) for key in SENTINEL_KEYS):
        raise SealedBootstrapError("sealed sentinel identity is invalid")
    if not _is_sha256_identity(document["environment_digest"]):
        raise SealedBootstrapError("sealed environment identity is invalid")
    files = document["files"]
    if not isinstance(files, list):
        raise SealedBootstrapError("sealed manifest files are not a list")
    for entry in files:
        if not isinstance(entry, dict) or "path" not in entry:
            raise SealedBootstrapError("sealed file entry shape is invalid")
    if files != sorted(files, key=lambda item: item["path"]):
        raise SealedBootstrapError("sealed manifest files are not sorted")
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or tuple(entry) != FILE_KEYS:
            raise SealedBootstrapError("sealed file entry shape is invalid")
        path = entry["path"]
        if (
            not isinstance(path, str)
            or path == MANIFEST_NAME
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or path in seen
        ):
            raise SealedBootstrapError(f"sealed file path is unsafe: {path!r}")
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise SealedBootstrapError(f"sealed file size is invalid: {path}")
        if not _is_sha256_identity(entry["sha256"]):
            raise SealedBootstrapError(f"sealed file digest is invalid: {path}")
        if not isinstance(entry["executable"], bool):
            raise SealedBootstrapError(f"sealed executable flag is invalid: {path}")
        seen.add(path)
    return document


def _expected_directories(files: Sequence[dict[str, Any]]) -> list[str]:
    expected: set[str] = set()
    for entry in files:
        parent = Path(str(entry["path"])).parent
        while str(parent) not in {"", "."}:
            expected.add(parent.as_posix())
            parent = parent.parent
    return sorted(expected)


def _actual_tree(root: Path) -> tuple[list[str], list[str]]:
    """Inventory every regular file and directory, rejecting unsafe entries."""
    files: list[str] = []
    directories: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if path.is_symlink() or _is_reparse_point(metadata):
            raise SealedBootstrapError(f"sealed tree contains a link: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            if metadata.st_mode & 0o222:
                raise SealedBootstrapError(f"sealed directory is writable: {relative}")
            directories.append(relative)
        elif stat.S_ISREG(metadata.st_mode):
            if relative == MANIFEST_NAME:
                continue
            if metadata.st_nlink != 1 or metadata.st_mode & 0o222:
                raise SealedBootstrapError(f"sealed file identity is unsafe: {relative}")
            if any(part == "__pycache__" for part in relative.split("/")) or path.suffix in {
                ".pyc",
                ".pyo",
            }:
                raise SealedBootstrapError(f"sealed bytecode is not allowed: {relative}")
            files.append(relative)
        else:
            raise SealedBootstrapError(f"sealed tree contains a special file: {relative}")
    return sorted(files), sorted(directories)


def _executable(path: Path, platform_name: str) -> bool:
    return bool(path.stat().st_mode & 0o111) or (
        platform_name == "windows" and path.suffix.lower() in {".exe", ".com", ".bat", ".cmd"}
    )


def _verify_tree(root: Path, document: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify exact files, bytes, permissions, links, and directory closure."""
    actual_files, actual_directories = _actual_tree(root)
    expected_files = [str(entry["path"]) for entry in document["files"]]
    if actual_files != expected_files:
        raise SealedBootstrapError("sealed environment has missing or extra files")
    if actual_directories != _expected_directories(document["files"]):
        raise SealedBootstrapError("sealed environment has missing or extra directories")
    records: list[dict[str, Any]] = []
    platform_name = str(document["platform"])
    for entry in document["files"]:
        path = _safe_inventory_path(root, str(entry["path"]))
        payload = path.read_bytes()
        actual = {
            "path": str(entry["path"]),
            "size": len(payload),
            "sha256": _sha256_bytes(payload),
            "executable": _executable(path, platform_name),
        }
        if actual != entry:
            raise SealedBootstrapError(f"sealed file changed: {entry['path']}")
        records.append(actual)
    compact = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if _sha256_bytes(compact) != document["environment_digest"]:
        raise SealedBootstrapError("sealed environment digest changed")
    return records


def _group_digest(entries: Sequence[dict[str, Any]]) -> str:
    payload = b"".join(
        f"{entry['path']}\0{entry['sha256']}\n".encode("utf-8") for entry in entries
    )
    if not payload:
        raise SealedBootstrapError("sealed sentinel group is empty")
    return _sha256_bytes(payload)


def _recomputed_sentinels(
    document: dict[str, Any], records: Sequence[dict[str, Any]]
) -> dict[str, str]:
    """Recompute the three sentinel groups from verified inventory bytes."""
    python_version = document["python_version"]
    if not isinstance(python_version, str):
        raise SealedBootstrapError("sealed Python version is malformed")
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


def _sentinels_match(
    root: Path, document: dict[str, Any], records: Sequence[dict[str, Any]]
) -> dict[str, str]:
    actual = _recomputed_sentinels(document, records)
    if document["sentinels"] != actual:
        raise SealedBootstrapError("sealed sentinel recomputation does not match manifest")
    for key, filename in SENTINEL_FILENAMES.items():
        path = _safe_inventory_path(root, f"sentinels/{filename}")
        if path.read_text(encoding="utf-8") != actual[key] + "\n":
            raise SealedBootstrapError(f"sealed sentinel marker changed: {path}")
    return actual


def _environment_root(value: str) -> Path:
    root = _assert_real_directory(Path(value), "sealed environment root")
    try:
        prefix = Path(sys.prefix).resolve(strict=True)
        base_prefix = Path(sys.base_prefix).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SealedBootstrapError("Python prefix contains an unsafe path") from exc
    if prefix != root / "venv" or base_prefix != root / "runtime":
        raise SealedBootstrapError("Python prefix is not bound to the supplied environment root")
    return root


def _load_manifest(root: Path, value: str) -> dict[str, Any]:
    expected = root / MANIFEST_NAME
    supplied = Path(value)
    try:
        supplied_resolved = supplied.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SealedBootstrapError("manifest path is unavailable") from exc
    if not supplied.is_absolute() or supplied_resolved != expected:
        raise SealedBootstrapError("manifest path is not bound to the environment root")
    _assert_regular_file(supplied, "sealed manifest")
    raw = supplied.read_bytes()
    expected_binding = os.environ.get(MANIFEST_SHA_ENV, "")
    if expected_binding and (
        not _is_sha256_identity(expected_binding)
        or _sha256_bytes(raw) != expected_binding
    ):
        raise SealedBootstrapError("sealed Python manifest binding changed")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SealedBootstrapError("sealed manifest is not valid UTF-8 JSON") from exc
    return _validate_manifest_shape(document)


def _new_dispatch_scope(
    root: Path,
    manifest: dict[str, Any],
    role: str,
) -> _SealedDispatchScope:
    """Create the process-private capability for one verified role target."""
    manifest_path = root / MANIFEST_NAME
    try:
        manifest_digest = _sha256_bytes(manifest_path.read_bytes())
    except OSError as exc:
        raise SealedBootstrapError("sealed manifest binding is unavailable") from exc
    return _SealedDispatchScope(
        _SCOPE_CONSTRUCTOR_TOKEN,
        root,
        manifest_path,
        manifest_digest,
        str(manifest["environment_digest"]),
        ROLE_TARGETS[role],
    )


def _attestation_destination(path_value: str, root: Path, nonce: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute() or path.name != f"startup-{nonce}.json":
        raise SealedBootstrapError("attestation path is not a fixed nonce-bound filename")
    parent = _assert_real_directory(
        path.parent,
        "attestation directory",
        require_immutable=False,
    )
    try:
        canonical = path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise SealedBootstrapError("attestation path is unavailable") from exc
    try:
        canonical.relative_to(root)
    except ValueError:
        pass
    else:
        raise SealedBootstrapError("attestation path may not be inside sealed environment")
    if path.parent != parent:
        raise SealedBootstrapError("attestation path contains a linked parent")
    if path.exists() or path.is_symlink():
        raise SealedBootstrapError("attestation destination already exists")
    return path


def _publish_attestation(path: Path, evidence: dict[str, Any]) -> None:
    """Write, fsync, and atomically publish a nonce-bound attestation."""
    payload = (json.dumps(evidence, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise SealedBootstrapError("attestation temporary destination already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() or path.is_symlink():
            raise SealedBootstrapError("attestation destination appeared during publish")
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise SealedBootstrapError("attestation destination appeared during publish") from exc
        # os.replace would permit an attacker to overwrite an existing target;
        # the link-and-unlink publication above is the no-replace equivalent.
        temporary.unlink()
        path.chmod(0o600)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    _assert_regular_file(
        path,
        "published attestation",
        require_immutable=False,
    )
    if path.stat().st_mode & 0o777 != 0o600:
        raise SealedBootstrapError("published attestation permissions are not private")


def _canonical_sys_path_entry(root: Path, value: object) -> str:
    """Normalize one import path and require it to remain in the snapshot."""
    if not isinstance(value, (str, os.PathLike)) or not os.fspath(value):
        raise SealedBootstrapError("isolated Python sys.path contains an empty entry")
    candidate = Path(os.fspath(value))
    if not candidate.is_absolute():
        raise SealedBootstrapError("isolated Python sys.path contains a relative entry")
    try:
        canonical = candidate.resolve(strict=True)
        canonical.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SealedBootstrapError(
            f"isolated Python sys.path escaped the sealed root: {value}"
        ) from exc
    return str(canonical)


def _normalize_sys_path(root: Path) -> list[str]:
    """Canonicalize import roots before the startup attestation is published."""
    snapshot = [_canonical_sys_path_entry(root, item) for item in sys.path]
    if not snapshot:
        raise SealedBootstrapError("isolated Python sys.path is empty")
    sys.path[:] = snapshot
    return snapshot


class _SealedSysPath(list[str]):
    """Keep later imports inside the already-verified snapshot."""

    def __init__(self, root: Path, values: Sequence[str]) -> None:
        self._root = root
        self._frozen = False
        super().__init__(values)

    def freeze(self) -> None:
        """Prevent the dispatched role from changing the attested path."""
        self._frozen = True

    def _ensure_mutable(self) -> None:
        if self._frozen:
            raise SealedBootstrapError("sealed sys.path changed after attestation")

    def _entry(self, value: object) -> str:
        return _canonical_sys_path_entry(self._root, value)

    def insert(self, index: int, value: str) -> None:
        self._ensure_mutable()
        super().insert(index, self._entry(value))

    def append(self, value: str) -> None:
        self._ensure_mutable()
        super().append(self._entry(value))

    def extend(self, values: Sequence[str]) -> None:
        self._ensure_mutable()
        super().extend(self._entry(value) for value in values)

    def __setitem__(self, index, value) -> None:
        self._ensure_mutable()
        if isinstance(index, slice):
            value = [self._entry(item) for item in value]
        else:
            value = self._entry(value)
        super().__setitem__(index, value)

    def __delitem__(self, index) -> None:
        self._ensure_mutable()
        super().__delitem__(index)

    def __iadd__(self, values: Sequence[str]):
        self._ensure_mutable()
        self.extend(values)
        return self

    def __imul__(self, value: int):
        self._ensure_mutable()
        return super().__imul__(value)

    def clear(self) -> None:
        self._ensure_mutable()
        super().clear()

    def pop(self, index: int = -1) -> str:
        self._ensure_mutable()
        return super().pop(index)

    def remove(self, value: str) -> None:
        self._ensure_mutable()
        super().remove(value)

    def reverse(self) -> None:
        self._ensure_mutable()
        super().reverse()

    def sort(self, *args: Any, **kwargs: Any) -> None:
        self._ensure_mutable()
        super().sort(*args, **kwargs)

def _validate_python_identity(root: Path) -> tuple[str, str, str]:
    """Validate executable and CPython prefixes against the sealed root."""
    try:
        executable = Path(sys.executable).resolve(strict=True)
        prefix = Path(sys.prefix).resolve(strict=True)
        base_prefix = Path(sys.base_prefix).resolve(strict=True)
        executable.relative_to(root)
        prefix.relative_to(root)
        base_prefix.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SealedBootstrapError("Python identity escaped the sealed root") from exc
    if prefix != root / "venv" or base_prefix != root / "runtime":
        raise SealedBootstrapError("Python prefixes are not bound to the sealed layout")
    if not executable.is_file() or executable.is_symlink():
        raise SealedBootstrapError("Python executable is not a sealed regular file")
    return str(executable), str(prefix), str(base_prefix)


def _reject_launch_environment_injection() -> None:
    """Reject inherited path and native-loader injection before role loading."""
    offenders = sorted(
        key
        for key in os.environ
        if key in FORBIDDEN_LAUNCH_ENVIRONMENTS
        or key.startswith("DYLD_")
        or key.startswith("LD_")
    )
    if offenders:
        raise SealedBootstrapError(
            "sealed launch environment contains forbidden injection keys: "
            + ", ".join(offenders)
        )


def _validate_runtime_state(root: Path) -> list[str]:
    """Validate prefixes, native import roots, and canonical sys.path."""
    _validate_python_identity(root)
    return _normalize_sys_path(root)


def _validate_post_dispatch_state(
    root: Path,
    expected_sys_path: Sequence[str],
    expected_object: _SealedSysPath,
) -> None:
    """Require the attested import path to remain unchanged through dispatch."""
    _validate_python_identity(root)
    if sys.path is not expected_object:
        raise SealedBootstrapError("sealed sys.path object was replaced after attestation")
    actual = [_canonical_sys_path_entry(root, item) for item in sys.path]
    if actual != list(expected_sys_path):
        raise SealedBootstrapError("sealed sys.path changed after attestation")


def _attestation(
    root: Path,
    role: str,
    nonce: str,
    document: dict[str, Any],
    sentinels: dict[str, str],
    sys_path: Sequence[str],
) -> dict[str, Any]:
    executable, prefix, base_prefix = _validate_python_identity(root)
    return {
        "schema": ATTESTATION_SCHEMA,
        "nonce": nonce,
        "role": role,
        "environment_digest": document["environment_digest"],
        "executable": str(executable),
        "prefix": str(prefix),
        "base_prefix": str(base_prefix),
        "sys_path": list(sys_path),
        "stdlib_sha256": sentinels["stdlib_sha256"],
        "site_packages_sha256": sentinels["site_packages_sha256"],
        "native_sha256": sentinels["native_sha256"],
        "lifetime_lease": True,
    }


class _LifetimeLease:
    """Hold a shared OS lock on ``lease.v1`` until the role exits."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "_LifetimeLease":
        _assert_regular_file(self.path, "sealed lifetime lease")
        handle = self.path.open("rb")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_RLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        except Exception:
            handle.close()
            raise
        self.handle = handle
        return self

    def __exit__(self, _exception_type, _exception, _traceback) -> None:
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def _load_role(root: Path, role: str):
    """Load one fixed wrapper from the sealed app subtree."""
    path = root / "app" / ROLE_ENTRYPOINTS[role]
    _assert_regular_file(path, f"sealed {role} role entrypoint")
    app_root = _assert_real_directory(root / "app", "sealed application root")
    target = app_root.joinpath(*ROLE_TARGETS[role])
    target = _assert_regular_file(
        target,
        f"canonical {role} target",
    )
    try:
        target.relative_to(app_root)
    except (OSError, ValueError) as exc:
        raise SealedBootstrapError(f"canonical {role} target escaped the app root") from exc
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    spec = importlib.util.spec_from_file_location(
        f"tobkiri_sealed_role_{role.replace('-', '_')}",
        path,
    )
    if spec is None or spec.loader is None:
        raise SealedBootstrapError(f"sealed role entrypoint is not importable: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, target


def _prepare_role(module: Any, scope: _SealedDispatchScope) -> Any:
    """Load the role target and perform its import-path preflight."""
    prepare = getattr(module, "prepare_for_dispatch", None)
    if not callable(prepare):
        raise SealedBootstrapError("sealed role wrapper lacks dispatch preparation")
    main = prepare(scope)
    if not callable(main):
        raise SealedBootstrapError("sealed role wrapper returned a non-callable main")
    return main


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tobkiri sealed Python bootstrap")
    parser.add_argument(
        "--role",
        choices=tuple(ROLE_ENTRYPOINTS),
        required=True,
    )
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--attestation", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--environment-root", required=True)
    return parser


def _split_arguments(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    values = list(argv)
    try:
        separator = values.index("--")
    except ValueError as exc:
        raise SealedBootstrapError("bootstrap requires -- before role arguments") from exc
    return values[:separator], values[separator + 1 :]


def main(argv: Sequence[str] | None = None) -> int:
    """Preload and verify one role, publish attestation, then dispatch it."""
    bootstrap_args, role_args = _split_arguments(
        list(argv) if argv is not None else sys.argv[1:]
    )
    args = _parser().parse_args(bootstrap_args)
    if len(args.nonce) != 64 or any(character not in "0123456789abcdef" for character in args.nonce):
        raise SealedBootstrapError("nonce must be the parent-provided 64-hex identity")
    _reject_launch_environment_injection()
    root = _environment_root(args.environment_root)
    manifest = _load_manifest(root, args.manifest)
    attestation_path = _attestation_destination(args.attestation, root, args.nonce)
    with _LifetimeLease(root / LEASE_NAME):
        records = _verify_tree(root, manifest)
        sentinels = _sentinels_match(root, manifest, records)
        _validate_runtime_state(root)
        scope = _new_dispatch_scope(root, manifest, args.role)
        role_module, target = _load_role(root, args.role)
        role_main = _prepare_role(role_module, scope)
        sys_path = _validate_runtime_state(root)
        sealed_sys_path = _SealedSysPath(root, sys_path)
        sys.path = sealed_sys_path
        evidence = _attestation(
            root,
            args.role,
            args.nonce,
            manifest,
            sentinels,
            sys_path,
        )
        _publish_attestation(attestation_path, evidence)
        sealed_sys_path.freeze()
        sys.argv = [str(target), *role_args]
        if args.role == "host_helper":
            result = int(role_main())
        else:
            result = int(role_main(role_args))
        _validate_post_dispatch_state(root, sys_path, sealed_sys_path)
        return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SealedBootstrapError, OSError, ValueError) as exc:
        print(f"sealed Python bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
