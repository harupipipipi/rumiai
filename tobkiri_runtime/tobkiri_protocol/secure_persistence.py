"""Pinned, descriptor-relative persistence for security-sensitive local state."""

from __future__ import annotations

import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .durability import replace_file_durable


class SecurePersistenceError(OSError):
    """Raised when a persistence root or entry cannot be used safely."""


_Identity = tuple[int, int]
_Fingerprint = tuple[int, int, int, int, int, int]
_ReadFingerprint = tuple[int, int, int, int, int, int, int, int]


def _identity(metadata: os.stat_result) -> _Identity:
    return (int(metadata.st_dev), int(metadata.st_ino))


def _fingerprint(metadata: os.stat_result) -> _Fingerprint:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_mode),
        int(metadata.st_nlink),
        int(getattr(metadata, "st_uid", 0)),
        int(metadata.st_size),
    )


def _read_fingerprint(metadata: os.stat_result) -> _ReadFingerprint:
    return (
        *_fingerprint(metadata),
        int(metadata.st_mtime_ns),
        int(metadata.st_ctime_ns),
    )


def _owned_regular(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_nlink == 1
        and (not hasattr(os, "getuid") or metadata.st_uid == os.getuid())
    )


def _owned_directory(metadata: os.stat_result) -> bool:
    return stat.S_ISDIR(metadata.st_mode) and (
        not hasattr(os, "getuid") or metadata.st_uid == os.getuid()
    )


class SecureDirectory:
    """Pin one owned directory tree and perform relative, no-follow operations.

    POSIX operations remain below descriptors opened from a captured ancestor
    chain. Windows keeps the same validation contract with before/after
    identity checks and delegates publication durability to ``MoveFileExW``.
    """

    def __init__(self, root: Path, *, create: bool = True) -> None:
        requested = Path(root)
        if not requested.is_absolute():
            requested = requested.absolute()
        self.root = requested
        self._chain = self._capture_chain(create=create)

    @staticmethod
    def _parts(relative: str | Path) -> tuple[str, ...]:
        candidate = Path(relative)
        if candidate.is_absolute() or not candidate.parts:
            raise SecurePersistenceError("persistence path must be relative")
        parts = tuple(candidate.parts)
        if any(part in {"", ".", ".."} for part in parts):
            raise SecurePersistenceError("persistence path is unsafe")
        return parts

    def _capture_chain(self, *, create: bool) -> tuple[tuple[Path, _Identity], ...]:
        if os.name == "nt":
            if create:
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            captured = self._capture_windows_chain()
            if not captured or captured[-1][0] != self.root:
                raise SecurePersistenceError("persistence root is unavailable")
            if not _owned_directory(self.root.lstat()):
                raise SecurePersistenceError("persistence root is unsafe")
            return captured

        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        current = Path(self.root.anchor)
        descriptors: list[int] = []
        posix_captured: list[tuple[Path, _Identity]] = []
        try:
            descriptor = os.open(current, flags)
            descriptors.append(descriptor)
            posix_captured.append((current, _identity(os.fstat(descriptor))))
            for component in self.root.parts[1:]:
                current = current / component
                try:
                    descriptor = os.open(component, flags, dir_fd=descriptors[-1])
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(component, mode=0o700, dir_fd=descriptors[-1])
                    descriptor = os.open(component, flags, dir_fd=descriptors[-1])
                descriptors.append(descriptor)
                posix_captured.append((current, _identity(os.fstat(descriptor))))
            root_metadata = os.fstat(descriptors[-1])
            if not _owned_directory(root_metadata):
                raise SecurePersistenceError("persistence root is unsafe")
            os.fchmod(descriptors[-1], 0o700)
            return tuple(posix_captured)
        except OSError as error:
            if isinstance(error, SecurePersistenceError):
                raise
            raise SecurePersistenceError("persistence ancestor is unsafe") from error
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def _capture_windows_chain(self) -> tuple[tuple[Path, _Identity], ...]:
        current = Path(self.root.anchor)
        paths = [current]
        for component in self.root.parts[1:]:
            current = current / component
            paths.append(current)
        captured: list[tuple[Path, _Identity]] = []
        for path in paths:
            metadata = path.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
                raise SecurePersistenceError("persistence ancestor is unsafe")
            captured.append((path, _identity(metadata)))
        return tuple(captured)

    def _validate_windows_chain(self) -> None:
        for path, expected in self._chain:
            try:
                metadata = path.lstat()
            except OSError as error:
                raise SecurePersistenceError(
                    "persistence ancestor identity changed"
                ) from error
            if (
                path.is_symlink()
                or not stat.S_ISDIR(metadata.st_mode)
                or _identity(metadata) != expected
            ):
                raise SecurePersistenceError("persistence ancestor identity changed")

    @contextmanager
    def _root_descriptor(self) -> Iterator[int]:
        if os.name == "nt":
            raise SecurePersistenceError("directory descriptors are unavailable on Windows")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptors: list[int] = []
        try:
            for index, (path, expected) in enumerate(self._chain):
                if index == 0:
                    descriptor = os.open(path, flags)
                else:
                    descriptor = os.open(
                        path.name,
                        flags,
                        dir_fd=descriptors[-1],
                    )
                descriptors.append(descriptor)
                if _identity(os.fstat(descriptor)) != expected:
                    raise SecurePersistenceError(
                        "persistence ancestor identity changed"
                    )
            yield descriptors[-1]
        except OSError as error:
            if isinstance(error, SecurePersistenceError):
                raise
            raise SecurePersistenceError("persistence ancestor is unsafe") from error
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    @contextmanager
    def _parent_descriptor(
        self, relative: str | Path, *, create: bool
    ) -> Iterator[tuple[int, str]]:
        parts = self._parts(relative)
        with self._root_descriptor() as root_descriptor:
            descriptors: list[int] = []
            current = root_descriptor
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                for component in parts[:-1]:
                    try:
                        descriptor = os.open(component, flags, dir_fd=current)
                    except FileNotFoundError:
                        if not create:
                            raise
                        os.mkdir(component, mode=0o700, dir_fd=current)
                        descriptor = os.open(component, flags, dir_fd=current)
                    metadata = os.fstat(descriptor)
                    if not _owned_directory(metadata):
                        os.close(descriptor)
                        raise SecurePersistenceError(
                            "persistence child directory is unsafe"
                        )
                    descriptors.append(descriptor)
                    current = descriptor
                yield current, parts[-1]
            finally:
                for descriptor in reversed(descriptors):
                    os.close(descriptor)

    @staticmethod
    def _stat_entry(
        parent_descriptor: int, name: str, *, required: bool
    ) -> os.stat_result | None:
        try:
            metadata = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if required:
                raise FileNotFoundError(name) from None
            return None
        if stat.S_ISLNK(metadata.st_mode):
            raise SecurePersistenceError("persistence entry is symlinked")
        if not _owned_regular(metadata):
            raise SecurePersistenceError("persistence entry identity is unsafe")
        return metadata

    def exists(self, relative: str | Path) -> bool:
        """Return whether one safe regular entry exists."""

        if os.name == "nt":
            self._validate_windows_chain()
            path = self.root.joinpath(*self._parts(relative))
            try:
                metadata = path.lstat()
            except FileNotFoundError:
                return False
            if path.is_symlink() or not _owned_regular(metadata):
                raise SecurePersistenceError("persistence entry identity is unsafe")
            self._validate_windows_chain()
            return True
        with self._parent_descriptor(relative, create=False) as (parent, name):
            return self._stat_entry(parent, name, required=False) is not None

    def read_bytes(self, relative: str | Path) -> bytes:
        """Read one owned single-link regular file with name/inode continuity."""

        if os.name == "nt":
            return self._read_bytes_windows(relative)
        with self._parent_descriptor(relative, create=False) as (parent, name):
            before = self._stat_entry(parent, name, required=True)
            assert before is not None
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent,
            )
            try:
                opened = os.fstat(descriptor)
                if not _owned_regular(opened) or _read_fingerprint(
                    opened
                ) != _read_fingerprint(before):
                    raise SecurePersistenceError("persistence entry changed before read")
                chunks: list[bytes] = []
                while True:
                    chunk = os.read(descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                after_open = os.fstat(descriptor)
                after_name = self._stat_entry(parent, name, required=True)
                assert after_name is not None
                if (
                    _read_fingerprint(after_open) != _read_fingerprint(opened)
                    or _read_fingerprint(after_name) != _read_fingerprint(opened)
                ):
                    raise SecurePersistenceError("persistence entry changed during read")
                return b"".join(chunks)
            finally:
                os.close(descriptor)

    def _read_bytes_windows(self, relative: str | Path) -> bytes:
        self._validate_windows_chain()
        path = self.root.joinpath(*self._parts(relative))
        before = path.lstat()
        if path.is_symlink() or not _owned_regular(before):
            raise SecurePersistenceError("persistence entry identity is unsafe")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not _owned_regular(opened) or _read_fingerprint(
                opened
            ) != _read_fingerprint(before):
                raise SecurePersistenceError("persistence entry changed before read")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = path.lstat()
            self._validate_windows_chain()
            if (
                _read_fingerprint(os.fstat(descriptor)) != _read_fingerprint(opened)
                or _read_fingerprint(after) != _read_fingerprint(opened)
            ):
                raise SecurePersistenceError("persistence entry changed during read")
            return b"".join(chunks)
        finally:
            os.close(descriptor)

    @staticmethod
    def _write_all(descriptor: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise SecurePersistenceError("persistence write was incomplete")
            view = view[written:]

    def write_bytes_atomic(self, relative: str | Path, data: bytes) -> None:
        """Durably replace one entry below the pinned tree."""

        if os.name == "nt":
            self._write_bytes_windows(relative, data)
            return
        with self._parent_descriptor(relative, create=True) as (parent, name):
            destination_before = self._stat_entry(parent, name, required=False)
            temporary = f".{name}.{os.getpid()}.{secrets.token_hex(16)}.tmp"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temporary, flags, 0o600, dir_fd=parent)
            published = False
            try:
                self._write_all(descriptor, data)
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
                temporary_open = os.fstat(descriptor)
                temporary_name = self._stat_entry(parent, temporary, required=True)
                assert temporary_name is not None
                if _fingerprint(temporary_open) != _fingerprint(temporary_name):
                    raise SecurePersistenceError("persistence temporary changed")
                destination_now = self._stat_entry(parent, name, required=False)
                if (
                    destination_before is None
                    and destination_now is not None
                    or destination_before is not None
                    and destination_now is None
                    or destination_before is not None
                    and destination_now is not None
                    and _fingerprint(destination_before) != _fingerprint(destination_now)
                ):
                    raise SecurePersistenceError(
                        "persistence destination changed before publication"
                    )
                os.replace(
                    temporary,
                    name,
                    src_dir_fd=parent,
                    dst_dir_fd=parent,
                )
                published = True
                destination_after = self._stat_entry(parent, name, required=True)
                assert destination_after is not None
                if _fingerprint(destination_after) != _fingerprint(temporary_open):
                    raise SecurePersistenceError(
                        "persistence destination changed during publication"
                    )
                os.fsync(parent)
            finally:
                os.close(descriptor)
                if not published:
                    try:
                        os.unlink(temporary, dir_fd=parent)
                    except FileNotFoundError:
                        pass

    def _write_bytes_windows(self, relative: str | Path, data: bytes) -> None:
        self._validate_windows_chain()
        parts = self._parts(relative)
        parent = self.root.joinpath(*parts[:-1])
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._validate_windows_chain()
        destination = parent / parts[-1]
        before: _Fingerprint | None = None
        try:
            metadata = destination.lstat()
            if destination.is_symlink() or not _owned_regular(metadata):
                raise SecurePersistenceError("persistence entry identity is unsafe")
            before = _fingerprint(metadata)
        except FileNotFoundError:
            pass
        temporary = parent / f".{destination.name}.{os.getpid()}.{secrets.token_hex(16)}.tmp"
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
            try:
                self._write_all(descriptor, data)
                os.fsync(descriptor)
                temporary_fingerprint = _fingerprint(os.fstat(descriptor))
            finally:
                os.close(descriptor)
            current: _Fingerprint | None = None
            try:
                current_metadata = destination.lstat()
                if destination.is_symlink() or not _owned_regular(current_metadata):
                    raise SecurePersistenceError("persistence entry identity is unsafe")
                current = _fingerprint(current_metadata)
            except FileNotFoundError:
                pass
            if current != before:
                raise SecurePersistenceError(
                    "persistence destination changed before publication"
                )
            replace_file_durable(temporary, destination)
            after = destination.lstat()
            self._validate_windows_chain()
            if _fingerprint(after) != temporary_fingerprint:
                raise SecurePersistenceError(
                    "persistence destination changed during publication"
                )
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def unlink(self, relative: str | Path, *, missing_ok: bool = False) -> None:
        """Remove one safe entry and durably flush the containing directory."""

        if os.name == "nt":
            self._validate_windows_chain()
            path = self.root.joinpath(*self._parts(relative))
            try:
                before = path.lstat()
            except FileNotFoundError:
                if missing_ok:
                    return
                raise
            if path.is_symlink() or not _owned_regular(before):
                raise SecurePersistenceError("persistence entry identity is unsafe")
            path.unlink()
            self._validate_windows_chain()
            return
        try:
            with self._parent_descriptor(relative, create=False) as (parent, name):
                posix_before = self._stat_entry(parent, name, required=not missing_ok)
                if posix_before is None:
                    return
                current = self._stat_entry(parent, name, required=True)
                assert current is not None
                if _fingerprint(current) != _fingerprint(posix_before):
                    raise SecurePersistenceError("persistence entry changed before unlink")
                os.unlink(name, dir_fd=parent)
                os.fsync(parent)
        except FileNotFoundError:
            if not missing_ok:
                raise

    def open_lock(self, relative: str | Path) -> int:
        """Open or create one owned single-link lock file below the pinned tree."""

        if os.name == "nt":
            self._validate_windows_chain()
            path = self.root.joinpath(*self._parts(relative))
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                self.validate_open_file(relative, descriptor)
                return descriptor
            except Exception:
                os.close(descriptor)
                raise
        with self._parent_descriptor(relative, create=True) as (parent, name):
            before = self._stat_entry(parent, name, required=False)
            flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            if before is None:
                flags |= os.O_CREAT | os.O_EXCL
            try:
                descriptor = os.open(name, flags, 0o600, dir_fd=parent)
            except FileExistsError as error:
                raise SecurePersistenceError(
                    "persistence lock changed before open"
                ) from error
            try:
                opened = os.fstat(descriptor)
                after = self._stat_entry(parent, name, required=True)
                assert after is not None
                if (
                    not _owned_regular(opened)
                    or _fingerprint(opened) != _fingerprint(after)
                    or before is not None
                    and _fingerprint(before) != _fingerprint(opened)
                ):
                    raise SecurePersistenceError("persistence lock identity is unsafe")
                os.fchmod(descriptor, 0o600)
                return descriptor
            except Exception:
                os.close(descriptor)
                raise

    def validate_open_file(self, relative: str | Path, descriptor: int) -> None:
        """Require an open descriptor to remain selected by its pinned name."""

        opened = os.fstat(descriptor)
        if not _owned_regular(opened):
            raise SecurePersistenceError("persistence open file identity is unsafe")
        if os.name == "nt":
            self._validate_windows_chain()
            path = self.root.joinpath(*self._parts(relative))
            named = path.lstat()
            if path.is_symlink() or _fingerprint(named) != _fingerprint(opened):
                raise SecurePersistenceError("persistence open file identity changed")
            self._validate_windows_chain()
            return
        with self._parent_descriptor(relative, create=False) as (parent, name):
            posix_named = self._stat_entry(parent, name, required=True)
            assert posix_named is not None
            if _fingerprint(posix_named) != _fingerprint(opened):
                raise SecurePersistenceError("persistence open file identity changed")
