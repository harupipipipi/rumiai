"""Descriptor-relative path guards for security-sensitive SQLite stores."""

from __future__ import annotations

import os
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from tobkiri_protocol.durability import publish_file_durable


class SecurePathError(RuntimeError):
    """Raised when a path cannot be proven safe for SQLite access."""


def canonical_platform_path(path: Path) -> Path:
    """Normalize only OS-owned compatibility aliases before path pinning.

    macOS exposes its protected temporary trees through root-owned ``/var`` and
    ``/tmp`` compatibility symlinks.  Resolving only those fixed aliases keeps
    standard-library temporary paths usable; all caller-controlled symlink
    ancestors remain visible to the no-follow walk and are rejected.
    """

    absolute = path.absolute()
    if sys.platform != "darwin":
        return absolute
    aliases = ((Path("/var"), Path("/private/var")), (Path("/tmp"), Path("/private/tmp")))
    for alias, canonical in aliases:
        if absolute != alias and alias not in absolute.parents:
            continue
        try:
            if alias.resolve(strict=True) != canonical:
                return absolute
        except OSError:
            return absolute
        return canonical / absolute.relative_to(alias)
    return absolute


@dataclass(frozen=True)
class FileIdentity:
    """Stable identity fields that must not change while a pathname is opened."""

    device: int
    inode: int
    owner: int
    file_type: int

    @classmethod
    def from_stat(cls, metadata: os.stat_result) -> "FileIdentity":
        """Build an identity from stat metadata."""

        return cls(
            device=metadata.st_dev,
            inode=metadata.st_ino,
            owner=getattr(metadata, "st_uid", 0),
            file_type=stat.S_IFMT(metadata.st_mode),
        )


def _validate_regular(metadata: os.stat_result) -> FileIdentity:
    if not stat.S_ISREG(metadata.st_mode):
        raise SecurePathError("file is not regular")
    if metadata.st_nlink != 1:
        raise SecurePathError("file does not have exactly one link")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise SecurePathError("file is not owned by the current user")
    return FileIdentity.from_stat(metadata)


def validate_owned_file_at(
    parent_descriptor: int,
    name: str,
    *,
    required: bool,
) -> os.stat_result | None:
    """Validate one descriptor-relative owned, single-link regular file."""

    try:
        metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        if required:
            raise SecurePathError("required file is unavailable") from None
        return None
    _validate_regular(metadata)
    return metadata


class SecureParent:
    """An opened parent directory plus its unresolved pathname identity."""

    def __init__(self, path: Path, descriptor: int | None) -> None:
        self.path = path
        self.descriptor = descriptor
        self.identity = FileIdentity.from_stat(
            os.fstat(descriptor) if descriptor is not None else path.stat()
        )

    def stat_file(self, name: str, *, required: bool) -> os.stat_result | None:
        """lstat one direct child and require an owned single-link regular file."""

        try:
            if self.descriptor is None:
                metadata = (self.path / name).lstat()
            else:
                return validate_owned_file_at(
                    self.descriptor,
                    name,
                    required=required,
                )
        except FileNotFoundError:
            if required:
                raise SecurePathError("required file is unavailable") from None
            return None
        _validate_regular(metadata)
        return metadata

    def open_file(self, name: str, flags: int, mode: int = 0o600) -> int:
        """Open one direct child without following a final symlink where supported."""

        guarded_flags = flags | getattr(os, "O_NOFOLLOW", 0)
        if self.descriptor is None:
            return os.open(self.path / name, guarded_flags, mode)
        return os.open(name, guarded_flags, mode, dir_fd=self.descriptor)

    def validate_open(
        self,
        name: str,
        *,
        required: bool,
        expected: FileIdentity | None = None,
    ) -> FileIdentity | None:
        """Validate pathname, opened descriptor, and pathname-after-open continuity."""

        before = self.stat_file(name, required=required)
        if before is None:
            return None
        before_identity = FileIdentity.from_stat(before)
        descriptor = self.open_file(name, os.O_RDONLY)
        try:
            opened_identity = _validate_regular(os.fstat(descriptor))
        finally:
            os.close(descriptor)
        after = self.stat_file(name, required=True)
        assert after is not None
        after_identity = FileIdentity.from_stat(after)
        if before_identity != opened_identity or opened_identity != after_identity:
            raise SecurePathError("file identity changed while opening")
        if expected is not None and opened_identity != expected:
            raise SecurePathError("file identity does not match the pinned file")
        return opened_identity

    def read_bytes(
        self,
        name: str,
        *,
        expected: FileIdentity | None = None,
    ) -> tuple[bytes, FileIdentity]:
        """Read a file through a verified descriptor and prove path continuity."""

        before = self.stat_file(name, required=True)
        assert before is not None
        before_identity = FileIdentity.from_stat(before)
        descriptor = self.open_file(name, os.O_RDONLY)
        try:
            opened_identity = _validate_regular(os.fstat(descriptor))
            with os.fdopen(os.dup(descriptor), "rb") as handle:
                payload = handle.read()
        finally:
            os.close(descriptor)
        after = self.stat_file(name, required=True)
        assert after is not None
        after_identity = FileIdentity.from_stat(after)
        if before_identity != opened_identity or opened_identity != after_identity:
            raise SecurePathError("file identity changed while reading")
        if expected is not None and opened_identity != expected:
            raise SecurePathError("file identity does not match the pinned file")
        return payload, opened_identity

    def create_empty_file(self, name: str) -> FileIdentity:
        """Create an owned, private, single-link regular file without following links."""

        descriptor = self.open_file(name, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            identity = _validate_regular(os.fstat(descriptor))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.assert_path_continuity()
        return self.validate_open(name, required=True, expected=identity) or identity

    def publish_new_file(self, source_name: str, destination_name: str) -> None:
        """Atomically publish a sibling without pathname re-resolution on POSIX."""

        if self.descriptor is None:
            publish_file_durable(
                self.path / source_name,
                self.path / destination_name,
            )
            return
        os.link(
            source_name,
            destination_name,
            src_dir_fd=self.descriptor,
            dst_dir_fd=self.descriptor,
            follow_symlinks=False,
        )
        os.unlink(source_name, dir_fd=self.descriptor)
        os.fsync(self.descriptor)

    def unlink_file(self, name: str, *, missing_ok: bool) -> None:
        """Unlink one sibling through the retained directory descriptor."""

        try:
            if self.descriptor is None:
                (self.path / name).unlink()
            else:
                os.unlink(name, dir_fd=self.descriptor)
        except FileNotFoundError:
            if not missing_ok:
                raise

    def assert_path_continuity(self) -> None:
        """Require the pathname to still resolve to the opened parent directory."""

        try:
            if os.name == "nt" or not os.supports_dir_fd:
                current_path = Path(self.path.anchor)
                for component in self.path.parts[1:]:
                    current_path /= component
                    current = current_path.lstat()
                    if current_path.is_symlink() or not stat.S_ISDIR(current.st_mode):
                        raise SecurePathError("ancestor is unsafe")
                current_identity = FileIdentity.from_stat(current)
            else:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(self.path.anchor or "/", flags)
                try:
                    for component in self.path.parts[1:]:
                        next_descriptor = os.open(component, flags, dir_fd=descriptor)
                        os.close(descriptor)
                        descriptor = next_descriptor
                    current_identity = FileIdentity.from_stat(os.fstat(descriptor))
                finally:
                    os.close(descriptor)
        except OSError as error:
            raise SecurePathError("parent directory is unavailable") from error
        if current_identity != self.identity:
            raise SecurePathError("parent directory identity changed")


@contextmanager
def secure_parent(path: Path) -> Iterator[SecureParent]:
    """Open every ancestor without symlink traversal and retain the final parent."""

    parent = path.absolute().parent
    if os.name == "nt" or not os.supports_dir_fd:
        current = Path(parent.anchor)
        try:
            for component in parent.parts[1:]:
                current /= component
                metadata = current.lstat()
                if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                    raise SecurePathError("ancestor is unsafe")
            yield SecureParent(parent, None)
            return
        except OSError as error:
            raise SecurePathError("ancestor is unavailable") from error

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(parent.anchor or "/", flags)
    try:
        for component in parent.parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        opened_parent = SecureParent(parent, descriptor)
        yield opened_parent
        opened_parent.assert_path_continuity()
    except SecurePathError:
        raise
    except OSError as error:
        raise SecurePathError("ancestor is unsafe") from error
    finally:
        os.close(descriptor)
