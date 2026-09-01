"""Receipt-gated local Git mutation without publication authority."""

from __future__ import annotations

import hashlib
import os
import re
import selectors
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

AUTHORITY = "rumi.service.host.authorize.v1"
GIT_READ = "rumi.service.git.read.v1"
WORKSPACE = "rumi.resource.workspace.v1"
SERVICE_PACK_ID = "rumi_git_write_pack"
_RESTRICTED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    ".npmrc",
    ".pypirc",
}
_MAX_STAGE_BYTES = 64 * 1024 * 1024
_MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
_MAX_SNAPSHOT_PATHS = 4_096
_MAX_SNAPSHOT_STATUS_BYTES = 8 * 1024 * 1024
_MAX_SNAPSHOT_PATH_LIST_BYTES = 8 * 1024 * 1024


class GitWriteService:
    """Apply finite local Git mutations after exact receipt redemption."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def invoke(self, name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Apply stage, commit, branch, or restore without network access."""
        if name not in {"stage", "commit", "branch_create", "branch_switch", "restore"}:
            raise ValueError(f"unknown Git write operation: {name}")
        if name in {"restore", "branch_create", "branch_switch"}:
            # These operations update the caller's worktree and/or live index.
            # A Host-enforced workspace lease (or a filesystem CAS over the
            # complete preimage) is required to make that final write safe.
            # This Pack has neither contract surface, so it must fail before
            # taking a receipt or starting any Git subprocess.
            raise PermissionError(
                f"Git {name.replace('_', ' ')} is unavailable until the Host provides an "
                "exclusive workspace mutation lease"
            )
        arguments = _arguments(name, payload)
        root, repository = self._roots(payload)
        _assert_repository_oid_widths(repository, arguments)
        _assert_repository_snapshot(repository, arguments)
        self._redeem(name, payload, arguments)
        if name == "stage":
            _assert_repository_snapshot(repository, arguments)
            paths = _stage(repository, arguments)
            return {"staged": paths, "published": False}
        if name == "commit":
            _assert_commit_effect_preconditions(repository, arguments)
            return self._commit(repository, arguments)
        raise AssertionError(f"unhandled Git write operation: {name}")

    def _commit(self, repository: Path, arguments: Mapping[str, Any]) -> dict[str, Any]:
        message = str(arguments["message"])
        entries = list(arguments["expected_commit_entries"])
        _materialize_captured_entries(repository, entries)
        with tempfile.TemporaryDirectory(prefix="tobkiri-git-index-") as temp:
            index_path = Path(temp) / "index"
            environment = {**os.environ, "GIT_INDEX_FILE": str(index_path)}
            _git(repository, ["read-tree", arguments["expected_head"]], env=environment)
            _apply_exact_entries(repository, entries, environment)
            tree = _git(repository, ["write-tree"], env=environment).strip()
            commit_hash = _git(
                repository,
                [
                    "commit-tree",
                    tree,
                    "-p",
                    arguments["expected_head"],
                    "-m",
                    message,
                ],
                env=environment,
            ).strip()
        # `update-ref` targets the receipt's explicit branch ref, never the
        # mutable symbolic name HEAD.  Its old-OID condition is the ref CAS;
        # the attached-ref check immediately before it rejects a detached or
        # switched worktree without letting that switch redirect the update.
        _assert_symbolic_head(repository, arguments["expected_head_ref"])
        _git(
            repository,
            [
                "update-ref",
                arguments["expected_head_ref"],
                commit_hash,
                arguments["expected_head"],
            ],
        )
        return {
            "commit_hash": commit_hash,
            "message": message,
            "paths": [str(entry["path"]) for entry in entries],
            "all_tracked": bool(arguments["all_tracked"]),
            "published": False,
        }

    def _roots(self, payload: Mapping[str, Any]) -> tuple[Path, Path]:
        mount = self.client.invoke(
            WORKSPACE,
            "get",
            {
                "profile_id": _profile(payload),
                "workspace_id": str(payload.get("workspace_id") or ""),
            },
        )
        if not isinstance(mount, Mapping):
            raise KeyError("workspace mount is unknown")
        if int(mount.get("mount_revision") or 0) != int(
            payload.get("expected_mount_revision") or -1
        ):
            raise PermissionError("workspace mount revision changed")
        root = Path(str(mount.get("root_path") or "")).resolve(strict=True)
        read = self.client.invoke(
            GIT_READ,
            "root",
            {
                "profile_id": _profile(payload),
                "workspace_id": str(payload.get("workspace_id") or ""),
            },
        )
        relative = str(read.get("repository_root") or ".")
        repository = (root / relative).resolve(strict=True)
        try:
            repository.relative_to(root)
        except ValueError as exc:
            raise PermissionError("Git repository root escapes workspace") from exc
        return root, repository

    def _redeem(self, name: str, payload: Mapping[str, Any], arguments: Mapping[str, Any]) -> None:
        result = self.client.invoke(
            AUTHORITY,
            "redeem",
            {
                "receipt": str(payload.get("authority_receipt") or ""),
                "service_pack_id": SERVICE_PACK_ID,
                "operation": f"git.{name}",
                "authority": "git.write",
                "caller_id": str(payload.get("caller_id") or ""),
                "caller_pack_id": str(payload.get("caller_pack_id") or ""),
                "caller_function_id": str(payload.get("caller_function_id") or ""),
                "profile_id": _profile(payload),
                "workspace_id": str(payload.get("workspace_id") or ""),
                "session_id": str(payload.get("session_id") or ""),
                "arguments": dict(arguments),
            },
        )
        if not result.get("authorized"):
            raise PermissionError(str(result.get("reason") or "Git write denied"))


def create_git_write_operation(
    client: Any,
) -> Callable[[str, Mapping[str, Any]], Any]:
    """Create receipt-gated local Git mutation operations."""
    return GitWriteService(client).invoke


def _arguments(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    expected_head = str(payload.get("expected_head") or "").strip()
    expected_tree = str(payload.get("expected_tree") or "").strip()
    expected_index_tree = str(payload.get("expected_index_tree") or "").strip()
    expected_status_hash = str(payload.get("expected_status_hash") or "").strip()
    expected_worktree_hash = str(payload.get("expected_worktree_hash") or "").strip()
    expected_mount_revision = int(payload.get("expected_mount_revision") or -1)
    if not all(
        (
            expected_head,
            expected_tree,
            expected_index_tree,
            expected_status_hash,
            expected_worktree_hash,
        )
    ) or (expected_mount_revision < 1):
        raise ValueError(
            "expected_head, expected_tree, expected_index_tree, "
            "expected_status_hash, expected_worktree_hash, and "
            "expected_mount_revision are required"
        )
    snapshot = {
        "expected_head": _oid(expected_head),
        "expected_tree": _oid(expected_tree),
        "expected_index_tree": _oid(expected_index_tree),
        "expected_status_hash": _oid(expected_status_hash),
        "expected_worktree_hash": _oid(expected_worktree_hash),
        "expected_mount_revision": expected_mount_revision,
    }
    if name in {"branch_create", "branch_switch"}:
        branch = str(payload.get("branch") or payload.get("name") or "").strip()
        if not branch:
            raise ValueError("Git branch is required")
        expected_branch_oid = _oid_or_zero(payload.get("expected_branch_oid"))
        if name == "branch_create" and not _is_zero_oid(expected_branch_oid):
            raise ValueError("Git branch must be absent at approval time")
        if name == "branch_switch" and _is_zero_oid(expected_branch_oid):
            raise ValueError("Git branch must exist at approval time")
        return {
            "branch": branch,
            "expected_branch_oid": expected_branch_oid,
            **snapshot,
        }
    paths = payload.get("paths") or payload.get("files") or []
    if not isinstance(paths, list):
        raise ValueError("Git paths must be a list")
    normalized_paths = [_validated_path(str(item)) for item in paths]
    result: dict[str, Any] = {"paths": normalized_paths, **snapshot}
    if name == "commit":
        message = str(payload.get("message") or "").strip()
        if not message or len(message) > 10_000:
            raise ValueError("Git commit message is invalid")
        expected_head_ref = _head_ref(str(payload.get("expected_head_ref") or ""))
        entries = _commit_entries_argument(
            payload.get("expected_commit_entries"),
            normalized_paths if normalized_paths else None,
        )
        result.update(
            {
                "message": message,
                "all_tracked": bool(payload.get("all_tracked", False)),
                "expected_head_ref": expected_head_ref,
                "expected_commit_entries": entries,
            }
        )
        if result["paths"] and result["all_tracked"]:
            raise ValueError("paths and all_tracked cannot be combined")
        if not result["paths"] and not result["all_tracked"]:
            raise ValueError("commit requires explicit paths or all_tracked")
    if name == "restore":
        result["source"] = str(payload.get("source") or "")
        result["expected_restore_tree"] = _oid(str(payload.get("expected_restore_tree") or ""))
    if name in {"stage", "restore"}:
        result["expected_path_entries"] = _path_entries_argument(
            payload.get("expected_path_entries"),
            result["paths"],
        )
    if not result["paths"] and name in {"stage", "restore"}:
        raise ValueError("explicit Git paths are required")
    return result


def _paths(repository: Path, values: list[str], *, allow_missing: bool) -> list[str]:
    result = []
    for value in values:
        normalized = _validated_path(str(value))
        raw = Path(normalized)
        if raw.is_absolute() or ".." in raw.parts or ".git" in raw.parts:
            raise PermissionError("Git path escapes or targets metadata")
        if raw.name.casefold() in _RESTRICTED_NAMES or raw.suffix.casefold() in {
            ".pem",
            ".key",
            ".p12",
        }:
            raise PermissionError("Git path is credential-sensitive")
        root_fd, parent_fd, filename = _open_verified_parent(repository, normalized)
        try:
            try:
                os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                if not allow_missing:
                    raise FileNotFoundError("Git path is unavailable") from None
            _assert_parent_chain_stable(root_fd, parent_fd, normalized)
        finally:
            os.close(parent_fd)
            os.close(root_fd)
        result.append(raw.as_posix())
    return result


def _validated_path(value: str) -> str:
    """Validate a relative index path before it reaches index-info."""

    raw = Path(str(value))
    if raw.is_absolute() or ".." in raw.parts or ".git" in raw.parts:
        raise PermissionError("Git path escapes or targets metadata")
    normalized = raw.as_posix()
    if not normalized or any(character in normalized for character in "\x00\r\n\t"):
        raise PermissionError("Git path contains an unsafe index delimiter")
    if Path(normalized).name.casefold() in _RESTRICTED_NAMES or Path(
        normalized
    ).suffix.casefold() in {".pem", ".key", ".p12"}:
        raise PermissionError("Git path is credential-sensitive")
    return normalized


def _head_ref(value: str) -> str:
    """Validate the symbolic branch ref captured for a commit receipt."""

    normalized = str(value or "").strip()
    if not re.fullmatch(r"refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", normalized):
        raise ValueError("Git commit requires an attached local branch snapshot")
    if ".." in normalized or "//" in normalized or normalized.endswith((".", "/")):
        raise ValueError("Git commit branch snapshot is invalid")
    return normalized


def _path_entries_argument(value: Any, paths: list[str]) -> list[dict[str, str]]:
    """Validate the exact worktree blobs embedded in a receipt scope."""

    if not isinstance(value, list) or len(value) != len(paths):
        raise ValueError("Git path entries are required for every Git path")
    entries: list[dict[str, str]] = []
    for path, raw in zip(paths, value, strict=True):
        if not isinstance(raw, Mapping) or str(raw.get("path") or "") != path:
            raise ValueError("Git path entries do not match requested paths")
        blob_oid = str(raw.get("blob_oid") or "").strip().lower()
        mode = str(raw.get("mode") or "").strip()
        if not blob_oid and not mode:
            entries.append({"path": path, "blob_oid": "", "mode": ""})
            continue
        if not blob_oid or mode not in {"100644", "100755", "120000"}:
            raise ValueError("Git path entry is invalid")
        entries.append({"path": path, "blob_oid": _oid(blob_oid), "mode": mode})
    return entries


def _commit_entries_argument(
    value: Any,
    requested_paths: list[str] | None,
) -> list[dict[str, str]]:
    """Validate the raw blob entries captured before commit approval.

    The path, mode, and raw blob OID are part of the authority receipt scope.
    At the effect boundary the write Pack captures each approved path exactly
    once through a nofollow descriptor, verifies this OID, and writes only
    those captured bytes to the object database.
    """

    if not isinstance(value, list) or len(value) > _MAX_SNAPSHOT_PATHS:
        raise ValueError("Git commit entries are invalid")
    entries: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("Git commit entry is invalid")
        path = _validated_path(str(raw.get("path") or ""))
        blob_oid = str(raw.get("blob_oid") or "").strip().lower()
        mode = str(raw.get("mode") or "").strip()
        if not blob_oid and not mode:
            entries.append({"path": path, "blob_oid": "", "mode": ""})
            continue
        if not blob_oid or mode not in {"100644", "100755", "120000"}:
            raise ValueError("Git commit entry is invalid")
        entries.append(
            {
                "path": path,
                "blob_oid": _oid(blob_oid),
                "mode": mode,
            }
        )
    if requested_paths is not None and [entry["path"] for entry in entries] != requested_paths:
        raise ValueError("Git commit entries do not match requested paths")
    return entries


def _stage(repository: Path, arguments: Mapping[str, Any]) -> list[str]:
    """Stage receipt-bound blobs without rereading mutable path content."""

    paths = _paths(repository, arguments["paths"], allow_missing=True)
    expected = list(arguments["expected_path_entries"])
    _assert_worktree_entries(repository, paths, expected)

    # Capture every approved path through a stable nofollow descriptor before
    # writing anything to the object database.  A race can therefore only
    # cause rejection; it cannot leave raced bytes as an unreachable object.
    materialized: list[tuple[dict[str, str], bytes]] = []
    for entry in expected:
        if not entry["blob_oid"]:
            materialized.append((entry, b""))
            continue
        data, _, _ = _capture_stage_bytes(repository, entry["path"])
        blob_oid = _hash_captured_bytes(repository, data, write=False)
        if blob_oid != entry["blob_oid"]:
            raise PermissionError("Git worktree path changed during staging")
        materialized.append((entry, data))
    approved_entries: list[dict[str, str]] = []
    for entry, data in materialized:
        if entry["blob_oid"]:
            written_oid = _hash_captured_bytes(repository, data, write=True)
            if written_oid != entry["blob_oid"]:
                raise PermissionError("Git stage bytes do not match the receipt")
        approved_entries.append(entry)
    _publish_exact_index(
        repository,
        arguments["expected_index_tree"],
        approved_entries,
    )
    return paths


def _assert_worktree_entries(
    repository: Path,
    paths: list[str],
    expected: list[Mapping[str, str]],
) -> None:
    actual = _worktree_entries(repository, paths)
    if actual != [dict(entry) for entry in expected]:
        raise PermissionError("Git worktree paths changed after preflight")


def _worktree_entries(
    repository: Path,
    paths: list[str],
    *,
    object_format: str | None = None,
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    selected_format = object_format or _object_hash_format(repository)
    for path in paths:
        try:
            data, is_symlink, metadata = _capture_stage_bytes(repository, path)
        except FileNotFoundError:
            entries.append({"path": path, "blob_oid": "", "mode": ""})
            continue
        mode = "120000" if is_symlink else ("100755" if metadata.st_mode & 0o111 else "100644")
        blob_oid = _raw_blob_oid(data, object_format=selected_format)
        entries.append({"path": path, "blob_oid": blob_oid, "mode": mode})
    return entries


def _capture_stage_bytes(
    repository: Path,
    path: str,
) -> tuple[bytes, bool, os.stat_result]:
    """Read one final component through verified nofollow directory FDs."""

    root_fd, parent_fd, filename = _open_verified_parent(repository, path)
    try:
        before = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode):
            data = os.readlink(filename, dir_fd=parent_fd).encode(
                "utf-8",
                errors="surrogateescape",
            )
            after = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
            if _file_identity(before) != _file_identity(after):
                raise PermissionError("Git symlink changed during staging")
            if len(data) > _MAX_STAGE_BYTES:
                raise ValueError("Git stage input exceeds maximum size")
            _assert_parent_chain_stable(root_fd, parent_fd, path)
            return data, True, before
        descriptor = _open_nofollow(filename, os.O_RDONLY, dir_fd=parent_fd)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise PermissionError("Git path is not a regular file")
            if opened.st_size > _MAX_STAGE_BYTES:
                raise ValueError("Git stage input exceeds maximum size")
            chunks: list[bytes] = []
            remaining = _MAX_STAGE_BYTES
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ValueError("Git stage input exceeds maximum size")
            closed = os.fstat(descriptor)
            if _file_identity(opened) != _file_identity(closed):
                raise PermissionError("Git path changed during staging")
            _assert_parent_chain_stable(root_fd, parent_fd, path)
            return b"".join(chunks), False, opened
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)
        os.close(root_fd)


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    """Return fields that must remain stable while a stage input is captured."""

    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_mode),
        int(metadata.st_size),
        int(metadata.st_mtime_ns),
    )


def _open_verified_parent(repository: Path, path: str) -> tuple[int, int, str]:
    """Open every parent from the repository dirfd without following links."""

    _require_safe_dirfd_support()
    parts = Path(path).parts
    if not parts or parts[-1] in {"", "."}:
        raise PermissionError("Git path is not a final file component")
    root_fd = _open_nofollow(repository, os.O_RDONLY | os.O_DIRECTORY)
    current = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            try:
                child = _open_nofollow(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY,
                    dir_fd=current,
                )
            except OSError as exc:
                raise PermissionError("Git path ancestor is unavailable or unsafe") from exc
            os.close(current)
            current = child
        return root_fd, current, parts[-1]
    except BaseException:
        os.close(current)
        os.close(root_fd)
        raise


def _require_safe_dirfd_support() -> None:
    """Fail closed unless POSIX dirfd and nofollow primitives are present."""

    required = (os.open, os.stat, os.readlink)
    if any(function not in os.supports_dir_fd for function in required):
        raise PermissionError("Git staging requires POSIX dirfd support")
    if os.stat not in os.supports_follow_symlinks:
        raise PermissionError("Git staging requires nofollow stat support")
    if getattr(os, "O_DIRECTORY", None) is None or getattr(os, "O_NOFOLLOW", None) is None:
        raise PermissionError("Git staging requires nofollow directory support")


def _open_nofollow(
    path: str | Path,
    flags: int,
    *,
    dir_fd: int | None = None,
) -> int:
    """Open one component only when symlink traversal is rejected."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise PermissionError("Git staging requires nofollow descriptor support")
    return os.open(path, flags | nofollow, dir_fd=dir_fd)


def _assert_parent_chain_stable(root_fd: int, parent_fd: int, path: str) -> None:
    """Reject a rename or replacement of a parent after capture began.

    The original repository descriptor anchors the workspace boundary.  This
    rewalk never resolves an ambient path, so a parent-symlink replacement is
    detected before raw bytes become a Git object.
    """

    expected = _directory_identity(os.fstat(parent_fd))
    current = os.dup(root_fd)
    try:
        for component in Path(path).parts[:-1]:
            try:
                child = _open_nofollow(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY,
                    dir_fd=current,
                )
            except OSError as exc:
                raise PermissionError("Git path ancestor changed during staging") from exc
            os.close(current)
            current = child
        if _directory_identity(os.fstat(current)) != expected:
            raise PermissionError("Git path ancestor changed during staging")
    finally:
        os.close(current)


def _directory_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    """Return the immutable identity fields used for directory revalidation."""

    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        stat.S_IFMT(metadata.st_mode),
    )


def _hash_captured_bytes(
    repository: Path,
    data: bytes,
    *,
    write: bool,
) -> str:
    """Hash raw captured bytes without invoking repository clean filters."""

    args = ["hash-object"]
    if write:
        args.append("-w")
    args.extend(["--stdin", "--no-filters"])
    return _git_bytes(repository, args, input_bytes=data).decode("ascii").strip()


def _object_hash_format(repository: Path) -> str:
    """Read the Git object format once for in-process raw blob hashing."""

    value = _git(repository, ["rev-parse", "--show-object-format"]).strip()
    if value not in {"sha1", "sha256"}:
        raise PermissionError("Git object format is unsupported")
    return value


def _object_oid_width(object_format: str) -> int:
    """Return the object-ID width supported by one Git object format."""

    if object_format == "sha1":
        return 40
    if object_format == "sha256":
        return 64
    raise PermissionError("Git object format is unsupported")


def _zero_oid(repository: Path) -> str:
    """Return Git's format-correct absent-object sentinel for this repository."""

    return "0" * _object_oid_width(_object_hash_format(repository))


def _raw_blob_oid(data: bytes, *, object_format: str) -> str:
    """Compute a raw Git blob OID without repository clean filters."""

    digest = hashlib.new(object_format)
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def _materialize_captured_entries(
    repository: Path,
    entries: Sequence[Mapping[str, str]],
) -> None:
    """Capture then publish only receipt-bound raw blobs for one commit."""

    materialized: list[tuple[Mapping[str, str], bytes]] = []
    total_bytes = 0
    for entry in entries:
        if not entry["blob_oid"]:
            if _final_metadata(repository, entry["path"]) is not None:
                raise PermissionError("Git commit path changed after preflight")
            materialized.append((entry, b""))
            continue
        try:
            data, is_symlink, metadata = _capture_stage_bytes(
                repository,
                entry["path"],
            )
        except FileNotFoundError:
            raise PermissionError("Git commit path changed after preflight")
        mode = "120000" if is_symlink else ("100755" if metadata.st_mode & 0o111 else "100644")
        total_bytes += len(data)
        if total_bytes > _MAX_SNAPSHOT_BYTES:
            raise ValueError("Git commit snapshot exceeds maximum size")
        captured_oid = _hash_captured_bytes(repository, data, write=False)
        if captured_oid != entry["blob_oid"] or mode != entry["mode"]:
            raise PermissionError("Git commit path changed after preflight")
        materialized.append((entry, data))
    for entry, data in materialized:
        if not entry["blob_oid"]:
            continue
        written_oid = _hash_captured_bytes(repository, data, write=True)
        if written_oid != entry["blob_oid"]:
            raise PermissionError("Git commit snapshot bytes do not match its blob")


def _final_metadata(repository: Path, path: str) -> os.stat_result | None:
    """Read final-component metadata only through its verified parent dirfd."""

    root_fd, parent_fd, filename = _open_verified_parent(repository, path)
    try:
        try:
            metadata = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            metadata = None
        _assert_parent_chain_stable(root_fd, parent_fd, path)
        return metadata
    finally:
        os.close(parent_fd)
        os.close(root_fd)


def _apply_exact_entries(
    repository: Path,
    entries: Sequence[Mapping[str, str]],
    environment: Mapping[str, str],
) -> None:
    """Apply receipt entries to an isolated index using safe index-info rows."""

    if not entries:
        return
    _git(
        repository,
        ["update-index", "--index-info"],
        env=environment,
        input_text=_index_info_lines(repository, entries),
    )


def _publish_exact_index(
    repository: Path,
    expected_index_tree: str,
    entries: Sequence[Mapping[str, str]],
) -> None:
    """CAS-publish one complete approved index while holding Git's index lock.

    A sequence of live ``git update-index`` calls can merge an unselected
    concurrent mutation after the final snapshot check. Build the complete
    target index from the immutable approved tree, then replace the live index
    only while the standard Git ``index.lock`` excludes every Git index writer.
    """

    index_path = _git_index_path(repository)
    if _git(repository, ["write-tree"]).strip() != expected_index_tree:
        raise PermissionError("Git index changed after preflight")
    captured_index = _index_identity(index_path)
    with _exclusive_index_lock(index_path):
        if _index_identity(index_path) != captured_index:
            raise PermissionError("Git index changed after preflight")
        with tempfile.TemporaryDirectory(
            prefix="tobkiri-git-index-",
            dir=index_path.parent,
        ) as temporary:
            planned_index = Path(temporary) / "index"
            environment = {**os.environ, "GIT_INDEX_FILE": str(planned_index)}
            _git(
                repository,
                ["read-tree", expected_index_tree],
                env=environment,
            )
            _git(
                repository,
                ["update-index", "--index-info"],
                env=environment,
                input_text=_index_info_lines(repository, entries),
            )
            _git(repository, ["write-tree"], env=environment)
            _fsync_file(planned_index)
            os.replace(planned_index, index_path)
            _fsync_directory(index_path.parent)


def _index_info_lines(
    repository: Path,
    entries: Sequence[Mapping[str, str]],
) -> str:
    """Build delimiter-safe index-info rows with format-correct deletions."""

    zero_oid = _zero_oid(repository)
    lines = []
    for entry in entries:
        if entry["blob_oid"]:
            lines.append(f"{entry['mode']} {entry['blob_oid']}\t{entry['path']}\n")
        else:
            lines.append(f"0 {zero_oid}\t{entry['path']}\n")
    return "".join(lines)


def _git_index_path(repository: Path) -> Path:
    """Resolve the real Git index path without trusting a caller path."""

    value = _git(repository, ["rev-parse", "--git-path", "index"]).strip()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repository / candidate
    return candidate.resolve(strict=False)


def _index_identity(index_path: Path) -> tuple[int, int, int, str] | None:
    """Return a byte and inode identity without asking Git to take index.lock."""

    try:
        descriptor = _open_nofollow(index_path, os.O_RDONLY)
    except FileNotFoundError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PermissionError("Git index is not a regular file")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        return (
            int(metadata.st_dev),
            int(metadata.st_ino),
            int(metadata.st_size),
            digest.hexdigest(),
        )
    finally:
        os.close(descriptor)


@contextmanager
def _exclusive_index_lock(index_path: Path):
    """Own Git's standard index lock for the full compare-and-publish window."""

    lock_path = index_path.with_name(index_path.name + ".lock")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise PermissionError("Git index is busy; retry after concurrent mutation") from exc
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _assert_symbolic_head(repository: Path, expected_head_ref: str) -> None:
    """Require the exact attached branch that was approved for this commit."""

    actual = _git(repository, ["symbolic-ref", "-q", "HEAD"]).strip()
    if actual != expected_head_ref:
        raise PermissionError("Git symbolic HEAD changed after preflight")


def _assert_commit_effect_preconditions(
    repository: Path,
    arguments: Mapping[str, Any],
) -> None:
    """Check ref identity after redemption without reopening mutable paths."""

    _assert_symbolic_head(repository, arguments["expected_head_ref"])
    head = _git(repository, ["rev-parse", "HEAD"]).strip()
    if head != arguments["expected_head"]:
        raise PermissionError("Git HEAD changed after preflight")


def _worktree_hash(repository: Path) -> str:
    """Hash raw candidate bytes without asking Git to interpret worktree data."""

    digest = hashlib.sha256()
    object_format = _object_hash_format(repository)
    paths = _workspace_candidate_paths(repository)
    for entry in _worktree_entries(
        repository,
        paths,
        object_format=object_format,
    ):
        _update_entry_digest(
            digest,
            entry["path"],
            entry["mode"],
            entry["blob_oid"],
        )
    return digest.hexdigest()


def _status_hash(repository: Path) -> str:
    """Bind safe index metadata without invoking `git status` or `git diff`."""

    return _git_digest(
        repository,
        ["ls-files", "--stage", "-z"],
        max_bytes=_MAX_SNAPSHOT_STATUS_BYTES,
    )


def _workspace_candidate_paths(repository: Path) -> list[str]:
    """List paths whose raw worktree values affect the approval snapshot."""

    output = _git_output_bounded(
        repository,
        [
            "ls-files",
            "--modified",
            "--deleted",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        max_bytes=_MAX_SNAPSHOT_PATH_LIST_BYTES,
    )
    paths = sorted(
        _validated_snapshot_path(item)
        for item in output.decode("utf-8", errors="surrogateescape").split("\0")
        if item
    )
    if len(paths) > _MAX_SNAPSHOT_PATHS:
        raise ValueError("Git snapshot has too many worktree changes")
    return paths


def _validated_snapshot_path(value: str) -> str:
    """Validate a discovered path without applying write-time secret policy."""

    path = Path(str(value))
    if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
        raise PermissionError("Git path escapes repository")
    normalized = path.as_posix()
    if not normalized or any(character in normalized for character in "\x00\r\n\t"):
        raise PermissionError("Git path contains an unsafe index delimiter")
    return normalized


def _update_entry_digest(
    digest: Any,
    path: str,
    mode: str,
    blob_oid: str,
) -> None:
    """Frame each snapshot entry so adjacent field values cannot collide."""

    for value in (
        path.encode("utf-8", errors="surrogateescape"),
        mode.encode("ascii"),
        blob_oid.encode("ascii"),
    ):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)


def _oid(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40,64}", normalized):
        raise ValueError("Git snapshot digest is invalid")
    return normalized


def _oid_or_zero(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if _is_zero_oid(normalized):
        return normalized
    return _oid(normalized)


def _is_zero_oid(value: str) -> bool:
    """Recognize only supported all-zero Git object-ID widths."""

    return len(value) in {40, 64} and value == "0" * len(value)


def _assert_repository_oid_widths(
    repository: Path,
    arguments: Mapping[str, Any],
) -> None:
    """Bind receipt object IDs to the repository's actual hash format."""

    object_width = _object_oid_width(_object_hash_format(repository))
    for field in (
        "expected_head",
        "expected_tree",
        "expected_index_tree",
        "expected_restore_tree",
        "expected_branch_oid",
    ):
        value = arguments.get(field)
        if value and len(str(value)) != object_width:
            raise PermissionError(f"Git {field} does not match the repository object format")
    for entries_field in ("expected_path_entries", "expected_commit_entries"):
        for entry in arguments.get(entries_field, []):
            blob_oid = str(entry.get("blob_oid") or "")
            if blob_oid and len(blob_oid) != object_width:
                raise PermissionError(
                    "Git receipt blob does not match the repository object format"
                )
    for field in ("expected_status_hash", "expected_worktree_hash"):
        if len(str(arguments[field])) != 64:
            raise PermissionError(f"Git {field} is not a SHA-256 digest")


def _assert_repository_snapshot(
    repository: Path,
    arguments: Mapping[str, Any],
) -> None:
    head = _git(repository, ["rev-parse", "HEAD"]).strip()
    tree = _git(repository, ["rev-parse", "HEAD^{tree}"]).strip()
    status_hash = _status_hash(repository)
    index_tree = _git(repository, ["write-tree"]).strip()
    worktree_hash = _worktree_hash(repository)
    if (
        head != arguments["expected_head"]
        or tree != arguments["expected_tree"]
        or index_tree != arguments["expected_index_tree"]
        or status_hash != arguments["expected_status_hash"]
        or worktree_hash != arguments["expected_worktree_hash"]
    ):
        raise PermissionError("Git repository snapshot changed")


def _git(
    repository: Path,
    args: list[str],
    *,
    env: Mapping[str, str] | None = None,
    input_text: str | None = None,
) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *_safe_git_args(args)],
        input=input_text,
        stdin=subprocess.DEVNULL if input_text is None else None,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=dict(env) if env is not None else None,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip() or "Git write failed")
    return completed.stdout


def _git_bytes(
    repository: Path,
    args: list[str],
    *,
    input_bytes: bytes,
    env: Mapping[str, str] | None = None,
) -> bytes:
    """Run Git with immutable binary stdin, preserving exact staged bytes."""

    completed = subprocess.run(
        ["git", "-C", str(repository), *_safe_git_args(args)],
        input=input_bytes,
        stdin=None,
        capture_output=True,
        text=False,
        timeout=60,
        check=False,
        env=dict(env) if env is not None else None,
    )
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout).decode("utf-8", errors="replace")
        raise RuntimeError(output.strip() or "Git write failed")
    return completed.stdout


def _git_digest(repository: Path, args: list[str], *, max_bytes: int) -> str:
    """Hash complete bounded Git output instead of silently truncating it."""

    digest = hashlib.sha256()
    _git_stream(repository, args, max_bytes=max_bytes, consume=digest.update)
    return digest.hexdigest()


def _git_output_bounded(
    repository: Path,
    args: list[str],
    *,
    max_bytes: int,
) -> bytes:
    """Return complete bounded machine output; reject oversized snapshots."""

    chunks: list[bytes] = []
    _git_stream(repository, args, max_bytes=max_bytes, consume=chunks.append)
    return b"".join(chunks)


def _git_stream(
    repository: Path,
    args: list[str],
    *,
    max_bytes: int,
    consume: Callable[[bytes], None],
) -> None:
    """Stream Git stdout under a hard cap while draining stderr safely."""

    process = subprocess.Popen(
        ["git", "-C", str(repository), *_safe_git_args(args)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    total = 0
    diagnostics = bytearray()
    deadline = time.monotonic() + 60
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.communicate()
                raise RuntimeError("Git snapshot timed out")
            for key, _ in selector.select(remaining):
                data = os.read(key.fd, 64 * 1024)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    total += len(data)
                    if total > max_bytes:
                        process.kill()
                        process.communicate()
                        raise ValueError("Git snapshot output exceeds maximum size")
                    consume(data)
                elif len(diagnostics) < 256_000:
                    diagnostics.extend(data[: 256_000 - len(diagnostics)])
        if process.wait(timeout=1) != 0:
            message = diagnostics.decode("utf-8", errors="replace").strip()
            raise RuntimeError(message or "Git write failed")
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.communicate()


def _profile(payload: Mapping[str, Any]) -> str:
    return str(payload.get("profile_id") or "default")


def _safe_git_args(args: list[str]) -> list[str]:
    """Disable repository-configured process hooks for local Git operations."""

    return [
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        *args,
    ]
