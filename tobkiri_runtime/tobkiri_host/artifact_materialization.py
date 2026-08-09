"""Digest-pinned, path-free Pack payloads for production isolation backends."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from tobkiri_protocol.canonical import canonical_digest
from tobkiri_protocol.validation import validate_file

from .contracts import ResolvedOperationBinding
from .errors import InvalidArtifactError
from .models import require_digest, require_identifier


_METADATA_FILES = (
    "artifact-index.v4.json",
    "contracts.v4.json",
    "executables.v4.json",
    "pack.v4.json",
)
_MAX_MATERIALIZED_FILES = 10_000
_MAX_MATERIALIZED_FILE_BYTES = 128 * 1024 * 1024
_MAX_MATERIALIZED_TOTAL_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class MaterializedArtifactFile:
    """One immutable regular file copied into the guest artifact namespace."""

    path: str
    digest: str
    executable: bool
    content: bytes

    def __post_init__(self) -> None:
        relative = PurePosixPath(self.path)
        if (
            not self.path
            or relative.is_absolute()
            or ".." in relative.parts
            or "." in relative.parts
            or "\\" in self.path
        ):
            raise InvalidArtifactError("materialized artifact path is unsafe")
        require_digest(self.digest, "materialized file")
        if len(self.content) > _MAX_MATERIALIZED_FILE_BYTES:
            raise InvalidArtifactError("materialized artifact file exceeds size limit")
        if _sha256(self.content) != self.digest:
            raise InvalidArtifactError("materialized artifact file digest mismatch")

    def request_payload(self) -> dict[str, Any]:
        """Return the bounded transport form without exposing a Host path."""

        return {
            "path": self.path,
            "digest": self.digest,
            "executable": self.executable,
            "content": base64.b64encode(self.content).decode("ascii"),
        }


@dataclass(frozen=True)
class MaterializedPackArtifact:
    """Authenticated Pack bytes captured for one exact Function binding."""

    pack_id: str
    artifact_digest: str
    function_id: str
    implementation_digest: str
    implementation_path: str
    materialization_digest: str
    root_device: int
    root_inode: int
    files: tuple[MaterializedArtifactFile, ...]

    def __post_init__(self) -> None:
        require_identifier(self.pack_id, "materialized pack_id")
        require_identifier(self.function_id, "materialized function_id")
        require_digest(self.artifact_digest, "materialized artifact")
        require_digest(self.implementation_digest, "materialized implementation")
        require_digest(self.materialization_digest, "materialization")
        if self.root_device < 0 or self.root_inode <= 0:
            raise InvalidArtifactError("materialized Pack root identity is invalid")
        if not self.files or len(self.files) > _MAX_MATERIALIZED_FILES:
            raise InvalidArtifactError("materialized artifact file inventory is invalid")
        if len({item.path for item in self.files}) != len(self.files):
            raise InvalidArtifactError("materialized artifact contains duplicate paths")
        if sum(len(item.content) for item in self.files) > _MAX_MATERIALIZED_TOTAL_BYTES:
            raise InvalidArtifactError("materialized artifact exceeds total size limit")
        implementations = [item for item in self.files if item.path == self.implementation_path]
        if len(implementations) != 1 or implementations[0].digest != self.implementation_digest:
            raise InvalidArtifactError("materialized implementation identity is unavailable")
        if self.materialization_digest != _materialization_digest(
            self.pack_id,
            self.artifact_digest,
            self.function_id,
            self.implementation_digest,
            self.implementation_path,
            self.files,
        ):
            raise InvalidArtifactError("materialization digest mismatch")

    def request_payload(self, *, nonce: str) -> dict[str, Any]:
        """Return a guest staging request containing identities and bytes only."""

        if len(nonce) != 64 or any(character not in "0123456789abcdef" for character in nonce):
            raise InvalidArtifactError("materialization nonce is invalid")
        return {
            "operation": "materialize",
            "pack_id": self.pack_id,
            "artifact_digest": self.artifact_digest,
            "function_id": self.function_id,
            "implementation_digest": self.implementation_digest,
            "implementation_path": self.implementation_path,
            "materialization_digest": self.materialization_digest,
            "materialization_nonce": nonce,
            "files": [item.request_payload() for item in self.files],
        }


def capture_materialized_artifact(
    pack_root: Path,
    binding: ResolvedOperationBinding,
) -> MaterializedPackArtifact:
    """Capture exact Pack bytes while rejecting symlink and swap races."""

    unresolved_root = Path(pack_root)
    try:
        initial_root = unresolved_root.lstat()
    except OSError as exc:
        raise InvalidArtifactError("Pack materialization root is unavailable") from exc
    if unresolved_root.is_symlink() or not stat.S_ISDIR(initial_root.st_mode):
        raise InvalidArtifactError("Pack materialization root must be a real directory")
    root = unresolved_root.resolve(strict=True)
    if binding.artifact.pack_id != root.name:
        raise InvalidArtifactError("Pack materialization root identity mismatch")

    manifest = validate_file(root / "pack.v4.json", "pack")
    index = validate_file(root / "artifact-index.v4.json", "pack_artifact_index")
    executable = validate_file(root / "executables.v4.json", "executable_catalog")
    if (
        manifest["pack"]["id"] != binding.artifact.pack_id
        or manifest["pack"]["artifact_digest"] != binding.artifact.digest
        or index["pack_id"] != binding.artifact.pack_id
        or executable["pack_id"] != binding.artifact.pack_id
    ):
        raise InvalidArtifactError("Pack materialization metadata identity mismatch")
    variants = [
        item
        for item in executable["variants"]
        if item["function_id"] == binding.function.function_id
        and item["variant_id"] == binding.variant.variant_id
        and item["implementation_digest"] == binding.function.implementation_digest
        and any(
            operation["contract_id"] == binding.operation.contract_id
            and operation["operation_id"] == binding.operation.operation_id
            for operation in item["operations"]
        )
    ]
    if len(variants) != 1:
        raise InvalidArtifactError("Pack materialization executable binding is ambiguous")
    implementation_path = str(variants[0]["implementation_path"])
    indexed = {
        str(item["path"]): str(item["digest"])
        for item in index["artifacts"]
    }
    requested_paths = tuple(sorted(set(indexed) | set(_METADATA_FILES)))
    files: list[MaterializedArtifactFile] = []
    if os.open not in os.supports_dir_fd:
        raise InvalidArtifactError(
            "secure descriptor-relative Pack materialization is unavailable"
        )
    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    root_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        root_descriptor = os.open(unresolved_root, root_flags)
    except OSError as exc:
        raise InvalidArtifactError("Pack materialization root is unavailable") from exc
    try:
        opened_root = os.fstat(root_descriptor)
        if _file_identity(initial_root) != _file_identity(opened_root):
            raise InvalidArtifactError("Pack materialization root changed before capture")
        for relative in requested_paths:
            content, mode = _read_regular_file(root_descriptor, relative)
            digest = _sha256(content)
            expected = indexed.get(relative)
            if expected is not None and not _constant_digest(digest, expected):
                raise InvalidArtifactError("Pack indexed artifact digest changed")
            files.append(
                MaterializedArtifactFile(
                    path=relative,
                    digest=digest,
                    executable=bool(mode & 0o111),
                    content=content,
                )
            )
    finally:
        os.close(root_descriptor)
    final_root = unresolved_root.lstat()
    if _file_identity(initial_root) != _file_identity(final_root):
        raise InvalidArtifactError("Pack materialization root changed during capture")
    captured = tuple(files)
    return MaterializedPackArtifact(
        pack_id=binding.artifact.pack_id,
        artifact_digest=binding.artifact.digest,
        function_id=binding.function.function_id,
        implementation_digest=binding.function.implementation_digest,
        implementation_path=implementation_path,
        materialization_digest=_materialization_digest(
            binding.artifact.pack_id,
            binding.artifact.digest,
            binding.function.function_id,
            binding.function.implementation_digest,
            implementation_path,
            captured,
        ),
        root_device=int(initial_root.st_dev),
        root_inode=int(initial_root.st_ino),
        files=captured,
    )


def _read_regular_file(root_descriptor: int, relative_value: str) -> tuple[bytes, int]:
    relative = PurePosixPath(relative_value)
    if (
        not relative_value
        or relative.is_absolute()
        or ".." in relative.parts
        or "." in relative.parts
        or "\\" in relative_value
    ):
        raise InvalidArtifactError("Pack materialization path is unsafe")
    parent_descriptor = os.dup(root_descriptor)
    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        for part in relative.parts[:-1]:
            try:
                next_descriptor = os.open(
                    part,
                    directory_flags,
                    dir_fd=parent_descriptor,
                )
            except OSError as exc:
                raise InvalidArtifactError(
                    "Pack materialization directory is unavailable"
                ) from exc
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor
            metadata = os.fstat(parent_descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise InvalidArtifactError("Pack materialization directory is unsafe")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(relative.parts[-1], flags, dir_fd=parent_descriptor)
        except OSError as exc:
            raise InvalidArtifactError("Pack materialization file is unavailable") from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise InvalidArtifactError("Pack materialization entry is not a regular file")
            if before.st_size > _MAX_MATERIALIZED_FILE_BYTES:
                raise InvalidArtifactError("Pack materialization file exceeds size limit")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(
                    descriptor,
                    min(1024 * 1024, _MAX_MATERIALIZED_FILE_BYTES + 1),
                )
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_MATERIALIZED_FILE_BYTES:
                    raise InvalidArtifactError(
                        "Pack materialization file exceeds size limit"
                    )
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if _file_identity(before) != _file_identity(after):
                raise InvalidArtifactError(
                    "Pack materialization file changed during capture"
                )
            return b"".join(chunks), stat.S_IMODE(before.st_mode)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_descriptor)


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (int(value.st_dev), int(value.st_ino), int(value.st_size), int(value.st_mtime_ns))


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _constant_digest(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)


def _materialization_digest(
    pack_id: str,
    artifact_digest: str,
    function_id: str,
    implementation_digest: str,
    implementation_path: str,
    files: tuple[MaterializedArtifactFile, ...],
) -> str:
    return canonical_digest(
        {
            "pack_id": pack_id,
            "artifact_digest": artifact_digest,
            "function_id": function_id,
            "implementation_digest": implementation_digest,
            "implementation_path": implementation_path,
            "files": [
                {
                    "path": item.path,
                    "digest": item.digest,
                    "executable": item.executable,
                    "size": len(item.content),
                }
                for item in files
            ],
        }
    )


__all__ = [
    "MaterializedArtifactFile",
    "MaterializedPackArtifact",
    "capture_materialized_artifact",
]
