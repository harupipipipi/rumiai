"""Scoped, fail-closed cleanup helpers for packaging workflows.

Windows packaging can briefly retain an executable after a child process has
exited.  Cleanup must tolerate only the small class of Windows sharing and
access-denied errors that can represent that race.  It must never turn an
arbitrary deletion error into a successful package, or remove a caller's
scope root by mistake.
"""

from __future__ import annotations

import errno
import ctypes
import os
import shutil
import stat
import subprocess
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Union


_IS_WINDOWS = os.name == "nt"
_REAL_WINDOWS = os.name == "nt"
_TRANSIENT_WINDOWS_WINERRORS = frozenset({5, 32, 33})
_TRANSIENT_WINDOWS_ERRNOS = frozenset({errno.EACCES, errno.EBUSY})
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_BACKOFF_SECONDS = (0.1, 0.25)
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_NOFOLLOW_UNSUPPORTED_ERRNOS = frozenset(
    {
        errno.EINVAL,
        errno.ENOSYS,
        getattr(errno, "ENOTSUP", errno.EINVAL),
    }
)
_WINDOWS_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_WINDOWS_DELETE = 0x00010000
_WINDOWS_FILE_READ_ATTRIBUTES = 0x00000080
_WINDOWS_FILE_LIST_DIRECTORY = 0x00000001
_WINDOWS_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_WINDOWS_FILE_SHARE_READ = 0x00000001
_WINDOWS_FILE_SHARE_WRITE = 0x00000002
_WINDOWS_FILE_SHARE_DELETE = 0x00000004
_WINDOWS_HANDLE_SHARE_MODE = _WINDOWS_FILE_SHARE_READ | _WINDOWS_FILE_SHARE_WRITE
_WINDOWS_OPEN_EXISTING = 3
_WINDOWS_FILE_RENAME_INFO_CLASS = 3
_WINDOWS_FILE_DISPOSITION_INFO_CLASS = 4
_WINDOWS_INVALID_HANDLE = ctypes.c_void_p(-1).value


class _WindowsByHandleFileInformation(ctypes.Structure):
    """Win32 BY_HANDLE_FILE_INFORMATION layout."""

    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


class _WindowsFileRenameInfo(ctypes.Structure):
    """Prefix of the variable-length FILE_RENAME_INFO structure."""

    _fields_ = [
        ("ReplaceIfExists", wintypes.BOOLEAN),
        ("RootDirectory", wintypes.HANDLE),
        ("FileNameLength", wintypes.DWORD),
        ("FileName", wintypes.WCHAR * 1),
    ]


class _WindowsFileDispositionInfo(ctypes.Structure):
    """FILE_DISPOSITION_INFO structure used for handle-bound deletion."""

    _fields_ = [("DeleteFile", wintypes.BOOLEAN)]


@dataclass(frozen=True)
class _WindowsFileIdentity:
    """Native volume/file identity and attributes for one open handle."""

    volume_serial: int
    file_index: int
    file_attributes: int


class _WindowsApi:
    """ctypes surface for no-delete-sharing handle-relative cleanup."""

    def __init__(self) -> None:
        if not _REAL_WINDOWS:
            raise RuntimeError("native Windows cleanup is unavailable on this host")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        self._create_file = kernel32.CreateFileW
        self._create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        self._create_file.restype = wintypes.HANDLE
        self._close_handle = kernel32.CloseHandle
        self._close_handle.argtypes = [wintypes.HANDLE]
        self._close_handle.restype = wintypes.BOOL
        self._get_file_information = kernel32.GetFileInformationByHandle
        self._get_file_information.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_WindowsByHandleFileInformation),
        ]
        self._get_file_information.restype = wintypes.BOOL
        self._set_file_information = kernel32.SetFileInformationByHandle
        self._set_file_information.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        self._set_file_information.restype = wintypes.BOOL

    @staticmethod
    def _last_error(path: Path) -> OSError:
        error = getattr(ctypes, "WinError")(getattr(ctypes, "get_last_error")())
        error.filename = os.fspath(path)
        return error

    def open(
        self,
        path: Path,
        *,
        directory: bool,
        share_mode: int = _WINDOWS_HANDLE_SHARE_MODE,
    ) -> int:
        """Open one final component without reparse or delete sharing."""

        if share_mode & _WINDOWS_FILE_SHARE_DELETE:
            raise ValueError("Windows cleanup handles must not share delete access")

        access = _WINDOWS_DELETE | _WINDOWS_FILE_READ_ATTRIBUTES
        flags = _WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT
        if directory:
            access |= _WINDOWS_FILE_LIST_DIRECTORY
            flags |= _WINDOWS_FILE_FLAG_BACKUP_SEMANTICS
        handle = self._create_file(
            os.fspath(path),
            access,
            share_mode,
            None,
            _WINDOWS_OPEN_EXISTING,
            flags,
            None,
        )
        value = getattr(handle, "value", handle)
        if value is None or int(value) == _WINDOWS_INVALID_HANDLE:
            raise self._last_error(path)
        return int(value)

    def close(self, handle: int) -> None:
        """Close one native handle."""

        if not self._close_handle(wintypes.HANDLE(handle)):
            raise self._last_error(Path("<native-handle>"))

    def identity(self, handle: int) -> _WindowsFileIdentity:
        """Read native volume/file identity and reparse attributes."""

        information = _WindowsByHandleFileInformation()
        if not self._get_file_information(
            wintypes.HANDLE(handle), ctypes.byref(information)
        ):
            raise self._last_error(Path("<native-handle>"))
        file_index = (int(information.nFileIndexHigh) << 32) | int(
            information.nFileIndexLow
        )
        return _WindowsFileIdentity(
            volume_serial=int(information.dwVolumeSerialNumber),
            file_index=file_index,
            file_attributes=int(information.dwFileAttributes),
        )

    def rename_relative(self, handle: int, parent_handle: int, name: str) -> None:
        """Atomically rename an open object relative to its open parent."""

        encoded_name = name.encode("utf-16-le")
        file_name_offset = _WindowsFileRenameInfo.FileName.offset
        buffer_size = file_name_offset + len(encoded_name)
        buffer = ctypes.create_string_buffer(buffer_size)
        information = ctypes.cast(
            buffer, ctypes.POINTER(_WindowsFileRenameInfo)
        ).contents
        information.ReplaceIfExists = wintypes.BOOLEAN(False)
        information.RootDirectory = wintypes.HANDLE(parent_handle)
        information.FileNameLength = len(encoded_name)
        ctypes.memmove(
            ctypes.addressof(buffer) + file_name_offset,
            encoded_name,
            len(encoded_name),
        )
        if not self._set_file_information(
            wintypes.HANDLE(handle),
            _WINDOWS_FILE_RENAME_INFO_CLASS,
            ctypes.cast(buffer, wintypes.LPVOID),
            buffer_size,
        ):
            raise self._last_error(Path(name))

    def mark_delete(self, handle: int) -> None:
        """Mark an open file or empty directory for deletion on close."""

        information = _WindowsFileDispositionInfo(DeleteFile=wintypes.BOOLEAN(True))
        if not self._set_file_information(
            wintypes.HANDLE(handle),
            _WINDOWS_FILE_DISPOSITION_INFO_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise self._last_error(Path("<native-handle>"))


_WINDOWS_API: Optional[_WindowsApi] = None
# Test-only seam.  Production callers leave this unset; tests can install a
# disposable-fixture callback to exercise the exact validation/mutation race.
_BEFORE_WINDOWS_QUARANTINE_MUTATION: Optional[Callable[[Path], None]] = None


def _get_windows_api(*, operation: str, path: Path) -> _WindowsApi:
    """Load the native API or fail closed on an actual Windows host."""

    global _WINDOWS_API
    if not _REAL_WINDOWS:
        raise _security_error(
            operation=operation,
            path=path,
            reason="native Windows cleanup is unavailable on this host",
        )
    if _WINDOWS_API is None:
        try:
            _WINDOWS_API = _WindowsApi()
        except (AttributeError, OSError, RuntimeError) as error:
            diagnostic = _diagnostic(
                operation=operation,
                path=path,
                attempts=0,
                error=error,
                reason="native handle-relative Windows cleanup is unavailable",
            )
            raise PackagingCleanupError(diagnostic) from error
    return _WINDOWS_API


@dataclass
class _WindowsBindingState:
    """Native handles bound to the original parent and target objects."""

    api: _WindowsApi
    ancestor_handles: tuple[tuple[Path, int, _WindowsFileIdentity], ...]
    target_handle: Optional[int]
    target_identity: Optional[_WindowsFileIdentity]
    target_is_directory: bool
    deletion_marked: bool = False

    @property
    def parent_handle(self) -> int:
        """Return the handle for the target's originally bound parent."""

        return self.ancestor_handles[-1][1]

    @property
    def parent_identity(self) -> _WindowsFileIdentity:
        """Return the identity for the target's originally bound parent."""

        return self.ancestor_handles[-1][2]

    def assert_current(self, *, operation: str, path: Path, attempts: int) -> None:
        """Reject native handle identity or reparse changes before mutation."""

        try:
            for ancestor_path, handle, expected in self.ancestor_handles:
                ancestor_identity = self.api.identity(handle)
                if ancestor_identity != expected:
                    raise _security_error(
                        operation=operation,
                        path=path,
                        reason=(
                            "bound Windows ancestor handle identity changed: "
                            f"{ancestor_path}"
                        ),
                        attempts=attempts,
                    )
                if (
                    not ancestor_identity.file_attributes
                    & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY
                ):
                    raise _security_error(
                        operation=operation,
                        path=path,
                        reason=f"bound Windows ancestor is no longer a directory: {ancestor_path}",
                        attempts=attempts,
                    )
                if ancestor_identity.file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                    raise _security_error(
                        operation=operation,
                        path=path,
                        reason=(
                            "bound Windows ancestor became a reparse point: "
                            f"{ancestor_path}"
                        ),
                        attempts=attempts,
                    )
            if self.target_handle is not None:
                target_identity = self.api.identity(self.target_handle)
                if target_identity != self.target_identity:
                    raise _security_error(
                        operation=operation,
                        path=path,
                        reason="bound Windows target handle identity changed",
                        attempts=attempts,
                    )
                if self.target_is_directory and not (
                    target_identity.file_attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY
                ):
                    raise _security_error(
                        operation=operation,
                        path=path,
                        reason="bound Windows target is no longer a directory",
                        attempts=attempts,
                    )
                if not self.target_is_directory and (
                    target_identity.file_attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY
                ):
                    raise _security_error(
                        operation=operation,
                        path=path,
                        reason="bound Windows target changed from a file to a directory",
                        attempts=attempts,
                    )
                if target_identity.file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                    raise _security_error(
                        operation=operation,
                        path=path,
                        reason="bound Windows target became a reparse point",
                        attempts=attempts,
                    )
        except PackagingCleanupError:
            raise
        except OSError as error:
            diagnostic = _diagnostic(
                operation=operation,
                path=path,
                attempts=attempts,
                error=error,
                reason="could not revalidate bound Windows handles",
            )
            raise PackagingCleanupError(diagnostic) from error

    def close(self) -> None:
        """Close target and parent handles after mutation or failure."""

        errors: list[OSError] = []
        if self.target_handle is not None:
            try:
                self.api.close(self.target_handle)
            except OSError as error:
                errors.append(error)
            self.target_handle = None
        for _ancestor_path, handle, _identity in reversed(self.ancestor_handles):
            try:
                self.api.close(handle)
            except OSError as error:
                errors.append(error)
        self.ancestor_handles = ()
        if errors:
            raise errors[0]


@dataclass(frozen=True)
class _PathIdentity:
    """Identity of one inspected component in an owned path chain."""

    path: Path
    exists: bool
    signature: tuple[Optional[int], Optional[int], int, Optional[int]]


@dataclass
class _PathBinding:
    """Validated path identities and any no-follow directory handles."""

    target: Path
    owner: Path
    identities: tuple[_PathIdentity, ...]
    directory_fds: tuple[int, ...] = ()
    windows_state: Optional[_WindowsBindingState] = None
    quarantine_path: Optional[Path] = None
    quarantine_signature: Optional[
        tuple[Optional[int], Optional[int], int, Optional[int]]
    ] = None

    @property
    def parent_fd(self) -> Optional[int]:
        """Return the held descriptor for the target's parent, if available."""

        return self.directory_fds[-1] if self.directory_fds else None

    def assert_current(self, *, operation: str, attempts: int) -> None:
        """Reject any component replacement since this binding was captured."""

        current = _capture_path_identities(
            self.target,
            self.owner,
            operation=operation,
            attempts=attempts,
        )
        if self.quarantine_path is None:
            identity_changed = current != self.identities
        else:
            identity_changed = (
                current[:-1] != self.identities[:-1]
                or current[-1].exists
                or self.quarantine_signature
                != _inspect_existing_identity(self.quarantine_path)
            )
        if identity_changed:
            raise PackagingCleanupError(
                _diagnostic(
                    operation=operation,
                    path=self.target,
                    attempts=attempts,
                    reason=("owned scope or path identity changed; cleanup refused"),
                )
            )
        if self.windows_state is not None:
            self.windows_state.assert_current(
                operation=operation,
                path=self.target,
                attempts=attempts,
            )

    def bind_quarantine(self, path: Path) -> None:
        """Bind a successful same-scope quarantine rename to its identity."""

        self.quarantine_path = path
        self.quarantine_signature = _inspect_existing_identity(path)

    def close(self) -> None:
        """Close all held directory descriptors from deepest to shallowest."""

        if self.windows_state is not None:
            try:
                self.windows_state.close()
            except OSError:
                # Native handle closure is best effort after the mutation or
                # an already-recorded failure.  All handles are attempted by
                # _WindowsBindingState.close before any error is suppressed.
                pass
        for descriptor in reversed(self.directory_fds):
            try:
                os.close(descriptor)
            except OSError:
                # Cleanup is already complete or already failing; descriptor
                # closure must not turn a useful packaging error into success.
                pass


@dataclass(frozen=True)
class CleanupDiagnostic:
    """Structured information about a refused or failed cleanup."""

    operation: str
    path: Path
    attempts: int
    error_type: Optional[str]
    error_message: Optional[str]
    errno: Optional[int]
    winerror: Optional[int]
    transient: bool
    exhausted: bool
    child_alive: bool = False
    reason: Optional[str] = None

    def format_message(self) -> str:
        """Return a concise diagnostic suitable for CI logs."""

        details = [
            f"{self.operation} failed for owned path {self.path}",
            f"attempts={self.attempts}",
        ]
        if self.reason:
            details.append(f"reason={self.reason}")
        if self.error_type:
            details.append(f"error={self.error_type}")
        if self.winerror is not None:
            details.append(f"winerror={self.winerror}")
        if self.errno is not None:
            details.append(f"errno={self.errno}")
        if self.error_message:
            details.append(self.error_message)
        return "; ".join(details)


class PackagingCleanupError(RuntimeError):
    """Raised when owned packaging output cannot be safely cleaned."""

    def __init__(self, diagnostic: CleanupDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.format_message())

    @property
    def path(self) -> Path:
        """Return the path whose cleanup was refused or failed."""

        return self.diagnostic.path

    @property
    def attempts(self) -> int:
        """Return the number of removal attempts made."""

        return self.diagnostic.attempts


def _diagnostic(
    *,
    operation: str,
    path: Path,
    attempts: int,
    error: Optional[BaseException] = None,
    transient: bool = False,
    exhausted: bool = False,
    child_alive: bool = False,
    reason: Optional[str] = None,
) -> CleanupDiagnostic:
    """Build a stable diagnostic without relying on platform-specific text."""

    return CleanupDiagnostic(
        operation=operation,
        path=path,
        attempts=attempts,
        error_type=type(error).__name__ if error else None,
        error_message=str(error) if error else None,
        errno=getattr(error, "errno", None) if error else None,
        winerror=getattr(error, "winerror", None) if error else None,
        transient=transient,
        exhausted=exhausted,
        child_alive=child_alive,
        reason=reason,
    )


def is_transient_windows_cleanup_error(
    error: OSError, *, platform_name: Optional[str] = None
) -> bool:
    """Return whether ``error`` is a recognized Windows lock race.

    The optional platform argument exists for deterministic tests.  On a real
    non-Windows host, access-denied errors are not retried because their cause
    and semantics differ from Windows sharing violations.
    """

    is_windows = _IS_WINDOWS if platform_name is None else platform_name.lower() == "nt"
    if not is_windows:
        return False
    return bool(
        getattr(error, "winerror", None) in _TRANSIENT_WINDOWS_WINERRORS
        or getattr(error, "errno", None) in _TRANSIENT_WINDOWS_ERRNOS
    )


def _absolute_lexical_path(path: Path) -> Path:
    """Normalize ``..`` without resolving symlinks or reparse points."""

    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _lstat_no_follow(path: Path) -> os.stat_result:
    """Inspect one path component without following its final link."""

    return os.lstat(path)


def _is_reparse_point(path: Path, result: os.stat_result) -> bool:
    """Return whether a component is a Windows reparse point or junction."""

    attributes = getattr(result, "st_file_attributes", 0) or 0
    if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        return True
    junction_checker = getattr(path, "is_junction", None)
    if callable(junction_checker):
        try:
            return bool(junction_checker())
        except OSError:
            # An uncertain junction check is unsafe for deletion.
            return True
    return False


def _security_error(
    *,
    operation: str,
    path: Path,
    reason: str,
    attempts: int = 0,
) -> PackagingCleanupError:
    """Create a typed fail-closed path-security error."""

    return PackagingCleanupError(
        _diagnostic(
            operation=operation,
            path=path,
            attempts=attempts,
            reason=reason,
        )
    )


def _identity_signature(
    result: os.stat_result,
) -> tuple[Optional[int], Optional[int], int, Optional[int]]:
    """Extract stable identity fields without depending on platform text."""

    return (
        getattr(result, "st_dev", None),
        getattr(result, "st_ino", None),
        stat.S_IFMT(result.st_mode),
        getattr(result, "st_file_attributes", None),
    )


def _inspect_existing_identity(
    path: Path,
    *,
    operation: str = "validate packaging quarantine",
    attempts: int = 0,
) -> Optional[tuple[Optional[int], Optional[int], int, Optional[int]]]:
    """Inspect a bound quarantine path without following its final component."""

    try:
        result = _lstat_no_follow(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(result.st_mode) or _is_reparse_point(path, result):
        raise _security_error(
            operation=operation,
            path=path,
            reason="quarantine path became a symlink or reparse point",
            attempts=attempts,
        )
    return _identity_signature(result)


def _capture_path_identities(
    target: Path,
    owner: Path,
    *,
    operation: str,
    attempts: int,
) -> tuple[_PathIdentity, ...]:
    """Inspect every owner-to-target component without following links."""

    try:
        relative_parts = target.relative_to(owner).parts
    except ValueError as error:
        raise _security_error(
            operation=operation,
            path=target,
            reason=f"path is outside owned scope {owner}",
            attempts=attempts,
        ) from error
    if not relative_parts:
        raise _security_error(
            operation=operation,
            path=target,
            reason="scope root itself is not removable",
            attempts=attempts,
        )

    components = [owner]
    current = owner
    for part in relative_parts:
        current /= part
        components.append(current)

    identities: list[_PathIdentity] = []
    root_device: Optional[int] = None
    last_index = len(components) - 1
    for index, component in enumerate(components):
        try:
            result = _lstat_no_follow(component)
        except FileNotFoundError as error:
            if index == last_index:
                identities.append(
                    _PathIdentity(
                        component,
                        False,
                        (None, None, 0, None),
                    )
                )
                break
            raise _security_error(
                operation=operation,
                path=target,
                reason=f"owned path ancestor disappeared: {component}",
                attempts=attempts,
            ) from error
        except OSError as error:
            diagnostic = _diagnostic(
                operation=operation,
                path=target,
                attempts=attempts,
                error=error,
                reason=f"could not inspect owned path component: {component}",
            )
            raise PackagingCleanupError(diagnostic) from error

        if stat.S_ISLNK(result.st_mode) or _is_reparse_point(component, result):
            raise _security_error(
                operation=operation,
                path=target,
                reason=f"symlink or reparse component is forbidden: {component}",
                attempts=attempts,
            )
        if index == 0:
            if not stat.S_ISDIR(result.st_mode):
                raise _security_error(
                    operation=operation,
                    path=target,
                    reason=f"owned scope root is not a directory: {component}",
                    attempts=attempts,
                )
            root_device = getattr(result, "st_dev", None)
        elif index < last_index and not stat.S_ISDIR(result.st_mode):
            raise _security_error(
                operation=operation,
                path=target,
                reason=f"owned path ancestor is not a directory: {component}",
                attempts=attempts,
            )

        component_device = getattr(result, "st_dev", None)
        if (
            root_device is not None
            and component_device is not None
            and component_device != root_device
        ):
            raise _security_error(
                operation=operation,
                path=target,
                reason=f"mount/device substitution is forbidden: {component}",
                attempts=attempts,
            )
        identities.append(
            _PathIdentity(
                component,
                True,
                _identity_signature(result),
            )
        )
    return tuple(identities)


def _open_parent_directories(
    target: Path,
    owner: Path,
    *,
    operation: str,
) -> tuple[int, ...]:
    """Hold POSIX no-follow directory handles through the removal attempt."""

    if _IS_WINDOWS:
        return ()
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
    if not all(hasattr(os, flag) for flag in required_flags):
        return ()
    relative_parts = target.relative_to(owner).parts
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    try:
        current = os.open(owner, flags)
        descriptors.append(current)
        for part in relative_parts[:-1]:
            current = os.open(part, flags, dir_fd=current)
            descriptors.append(current)
    except (NotImplementedError, TypeError, ValueError):
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        return ()
    except OSError as error:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        if error.errno in _NOFOLLOW_UNSUPPORTED_ERRNOS:
            return ()
        diagnostic = _diagnostic(
            operation=operation,
            path=target,
            attempts=0,
            error=error,
            reason="could not open owned path without following links",
        )
        raise PackagingCleanupError(diagnostic) from error
    return tuple(descriptors)


def _assert_native_identity_matches_path(
    native_identity: _WindowsFileIdentity,
    expected: _PathIdentity,
    *,
    directory: bool,
    operation: str,
    path: Path,
) -> None:
    """Bind an open Windows object to its already-lstatted path identity."""

    expected_inode = expected.signature[1]
    if expected_inode in (None, 0) or native_identity.file_index != expected_inode:
        raise _security_error(
            operation=operation,
            path=path,
            reason=(
                "Windows handle identity was unavailable or did not match "
                f"the validated path: {path}"
            ),
        )
    is_directory = bool(
        native_identity.file_attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY
    )
    if is_directory != directory:
        raise _security_error(
            operation=operation,
            path=path,
            reason=f"Windows handle type did not match validated path: {path}",
        )
    if native_identity.file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        raise _security_error(
            operation=operation,
            path=path,
            reason=f"Windows handle opened a reparse point: {path}",
        )


def _close_windows_handles(
    api: _WindowsApi,
    target_handle: Optional[int],
    ancestor_handles: Sequence[tuple[Path, int, _WindowsFileIdentity]],
) -> None:
    """Close every partially-created native binding after a failed bind."""

    if target_handle is not None:
        try:
            api.close(target_handle)
        except OSError:
            pass
    for _path, handle, _identity in reversed(ancestor_handles):
        try:
            api.close(handle)
        except OSError:
            pass


def _bind_windows_handles(
    target: Path,
    identities: tuple[_PathIdentity, ...],
    *,
    operation: str,
) -> _WindowsBindingState:
    """Hold read/write-only, no-reparse handles for the verified chain.

    ``CreateFileW`` does not provide an ordinary Python ``openat`` equivalent.
    Each component is therefore opened with ``OPEN_REPARSE_POINT`` and matched
    to the pre-open ``lstat`` identity, followed by an immediate full-chain
    recapture.  Every held handle excludes ``FILE_SHARE_DELETE`` so a
    competing delete/rename cannot substitute a path component while the
    chain is live.  Mutation itself is still handle-relative through
    ``SetFileInformationByHandle``; an identity mismatch fails closed rather
    than falling back to a pathname-based delete.
    """

    api = _get_windows_api(operation=operation, path=target)
    ancestor_handles: list[tuple[Path, int, _WindowsFileIdentity]] = []
    target_handle: Optional[int] = None
    try:
        for expected in identities[:-1]:
            if not expected.exists:
                raise _security_error(
                    operation=operation,
                    path=target,
                    reason=f"validated Windows ancestor disappeared: {expected.path}",
                )
            handle = api.open(
                expected.path,
                directory=True,
                share_mode=_WINDOWS_HANDLE_SHARE_MODE,
            )
            native_identity = api.identity(handle)
            _assert_native_identity_matches_path(
                native_identity,
                expected,
                directory=True,
                operation=operation,
                path=expected.path,
            )
            ancestor_handles.append((expected.path, handle, native_identity))

        expected_target = identities[-1]
        target_is_directory = bool(
            expected_target.exists and stat.S_ISDIR(expected_target.signature[2])
        )
        target_identity: Optional[_WindowsFileIdentity] = None
        if expected_target.exists:
            target_handle = api.open(
                target,
                directory=target_is_directory,
                share_mode=_WINDOWS_HANDLE_SHARE_MODE,
            )
            target_identity = api.identity(target_handle)
            _assert_native_identity_matches_path(
                target_identity,
                expected_target,
                directory=target_is_directory,
                operation=operation,
                path=target,
            )

        state = _WindowsBindingState(
            api=api,
            ancestor_handles=tuple(ancestor_handles),
            target_handle=target_handle,
            target_identity=target_identity,
            target_is_directory=target_is_directory,
        )
        current = _capture_path_identities(
            target,
            identities[0].path,
            operation=operation,
            attempts=0,
        )
        if current != identities:
            raise _security_error(
                operation=operation,
                path=target,
                reason=("owned path identity changed while binding Windows handles"),
            )
        state.assert_current(operation=operation, path=target, attempts=0)
        return state
    except BaseException:
        _close_windows_handles(api, target_handle, ancestor_handles)
        raise


def _bind_owned_path(
    path: Path,
    owner_root: Path,
    *,
    operation: str,
) -> _PathBinding:
    """Capture the path chain and bind no-follow parent handles where possible."""

    target = _absolute_lexical_path(path)
    owner = _absolute_lexical_path(owner_root)
    try:
        if target == owner or not target.is_relative_to(owner):
            raise _security_error(
                operation=operation,
                path=target,
                reason=f"path is outside owned scope {owner}",
            )
    except AttributeError as error:
        raise _security_error(
            operation=operation,
            path=target,
            reason="path containment check is unavailable on this interpreter",
        ) from error
    identities = _capture_path_identities(
        target,
        owner,
        operation=operation,
        attempts=0,
    )
    descriptors = _open_parent_directories(
        target,
        owner,
        operation=operation,
    )
    windows_state: Optional[_WindowsBindingState] = None
    try:
        if _REAL_WINDOWS:
            windows_state = _bind_windows_handles(
                target,
                identities,
                operation=operation,
            )
        binding = _PathBinding(
            target,
            owner,
            identities,
            descriptors,
            windows_state=windows_state,
        )
        binding.assert_current(operation=operation, attempts=0)
    except BaseException:
        if windows_state is not None:
            windows_state.close()
        else:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        raise
    return binding


def _assert_tree_has_no_reparse_points(
    root: Path,
    *,
    operation: str,
    root_device: Optional[int],
) -> None:
    """Inspect a quarantine tree without following links or mount points."""

    pending = [root]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            diagnostic = _diagnostic(
                operation=operation,
                path=current,
                attempts=0,
                error=error,
                reason="could not inspect quarantined packaging output",
            )
            raise PackagingCleanupError(diagnostic) from error
        for entry in entries:
            child = Path(entry.path)
            try:
                result = _lstat_no_follow(child)
            except OSError as error:
                diagnostic = _diagnostic(
                    operation=operation,
                    path=child,
                    attempts=0,
                    error=error,
                    reason="quarantined packaging entry changed during inspection",
                )
                raise PackagingCleanupError(diagnostic) from error
            if stat.S_ISLNK(result.st_mode) or _is_reparse_point(child, result):
                raise _security_error(
                    operation=operation,
                    path=child,
                    reason="quarantined tree contains a symlink or reparse point",
                )
            child_device = getattr(result, "st_dev", None)
            if (
                root_device is not None
                and child_device is not None
                and child_device != root_device
            ):
                raise _security_error(
                    operation=operation,
                    path=child,
                    reason="quarantined tree crosses a mount/device boundary",
                )
            if stat.S_ISDIR(result.st_mode):
                pending.append(child)


def _new_quarantine_path(path: Path, *, operation: str) -> Path:
    """Choose a fresh sibling quarantine name without following links."""

    for _ in range(8):
        candidate = path.parent / f".tobkiri-cleanup-{uuid.uuid4().hex}"
        try:
            _lstat_no_follow(candidate)
        except FileNotFoundError:
            return candidate
        except OSError as error:
            diagnostic = _diagnostic(
                operation=operation,
                path=candidate,
                attempts=0,
                error=error,
                reason="could not inspect quarantine destination",
            )
            raise PackagingCleanupError(diagnostic) from error
    raise _security_error(
        operation=operation,
        path=path,
        reason="could not allocate a unique quarantine destination",
    )


def _run_windows_mutation_hook(path: Path) -> None:
    """Run the deterministic pre-mutation test seam, when one is installed."""

    if _BEFORE_WINDOWS_QUARANTINE_MUTATION is not None:
        _BEFORE_WINDOWS_QUARANTINE_MUTATION(path)


def _open_windows_child_handle(
    api: _WindowsApi,
    path: Path,
    result: os.stat_result,
    *,
    operation: str,
) -> int:
    """Open and identity-bind one quarantined child without following links."""

    expected = _PathIdentity(path, True, _identity_signature(result))
    is_directory = stat.S_ISDIR(result.st_mode)
    handle = api.open(
        path,
        directory=is_directory,
        share_mode=_WINDOWS_HANDLE_SHARE_MODE,
    )
    try:
        native_identity = api.identity(handle)
        _assert_native_identity_matches_path(
            native_identity,
            expected,
            directory=is_directory,
            operation=operation,
            path=path,
        )
        return handle
    except BaseException:
        try:
            api.close(handle)
        except OSError:
            pass
        raise


def _assert_windows_directory_current(
    directory: Path,
    directory_handle: int,
    expected: _PathIdentity,
    *,
    binding: _PathBinding,
    operation: str,
    attempts: int,
) -> None:
    """Bind a recursive directory pathname to its held native handle."""

    binding.assert_current(operation=operation, attempts=attempts)
    try:
        result = _lstat_no_follow(directory)
    except OSError as error:
        diagnostic = _diagnostic(
            operation=operation,
            path=directory,
            attempts=attempts,
            error=error,
            reason="quarantined directory changed during handle-bound cleanup",
        )
        raise PackagingCleanupError(diagnostic) from error
    if stat.S_ISLNK(result.st_mode) or _is_reparse_point(directory, result):
        raise _security_error(
            operation=operation,
            path=directory,
            reason="quarantined directory became a symlink or reparse point",
            attempts=attempts,
        )
    if _identity_signature(result) != expected.signature:
        raise _security_error(
            operation=operation,
            path=directory,
            reason="quarantined directory pathname identity changed",
            attempts=attempts,
        )
    native_state = binding.windows_state
    if native_state is None:
        raise _security_error(
            operation=operation,
            path=directory,
            reason="native Windows directory handle state is unavailable",
            attempts=attempts,
        )
    native_identity = native_state.api.identity(directory_handle)
    _assert_native_identity_matches_path(
        native_identity,
        expected,
        directory=True,
        operation=operation,
        path=directory,
    )


def _remove_windows_tree_by_handles(
    root: Path,
    root_handle: int,
    *,
    binding: _PathBinding,
    operation: str,
    attempts: int,
    root_device: Optional[int],
) -> None:
    """Recursively delete a quarantined directory through bound handles.

    Python's ``shutil.rmtree`` is pathname-based on Windows and cannot prove
    that a redirected ancestor was not substituted between enumeration and
    deletion.  Each child below is therefore opened with an explicit
    no-reparse handle, matched to its pre-open ``lstat`` identity, and deleted
    by ``SetFileInformationByHandle``.  A directory that changes or becomes
    non-empty at its final handle operation fails closed.
    """

    state = binding.windows_state
    if state is None:
        raise _security_error(
            operation=operation,
            path=root,
            reason="native Windows tree deletion requires bound handles",
            attempts=attempts,
        )

    def remove_directory(
        directory: Path,
        directory_handle: int,
        expected: _PathIdentity,
    ) -> None:
        _assert_windows_directory_current(
            directory,
            directory_handle,
            expected,
            binding=binding,
            operation=operation,
            attempts=attempts,
        )

        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            diagnostic = _diagnostic(
                operation=operation,
                path=directory,
                attempts=attempts,
                error=error,
                reason="could not enumerate quarantined packaging output",
            )
            raise PackagingCleanupError(diagnostic) from error

        for entry in entries:
            child = Path(entry.path)
            _assert_windows_directory_current(
                directory,
                directory_handle,
                expected,
                binding=binding,
                operation=operation,
                attempts=attempts,
            )
            try:
                child_result = _lstat_no_follow(child)
            except OSError as error:
                diagnostic = _diagnostic(
                    operation=operation,
                    path=child,
                    attempts=attempts,
                    error=error,
                    reason="quarantined child changed before handle binding",
                )
                raise PackagingCleanupError(diagnostic) from error
            if stat.S_ISLNK(child_result.st_mode) or _is_reparse_point(
                child, child_result
            ):
                raise _security_error(
                    operation=operation,
                    path=child,
                    reason="quarantined tree contains a symlink or reparse point",
                    attempts=attempts,
                )
            child_device = getattr(child_result, "st_dev", None)
            if (
                root_device is not None
                and child_device is not None
                and child_device != root_device
            ):
                raise _security_error(
                    operation=operation,
                    path=child,
                    reason="quarantined tree crosses a mount/device boundary",
                    attempts=attempts,
                )

            child_handle = _open_windows_child_handle(
                state.api,
                child,
                child_result,
                operation=operation,
            )
            try:
                # This catches replacement of the bound quarantine root while
                # the child pathname was being opened.  The child handle also
                # remains identity-bound for the actual delete operation.
                _assert_windows_directory_current(
                    directory,
                    directory_handle,
                    expected,
                    binding=binding,
                    operation=operation,
                    attempts=attempts,
                )
                if stat.S_ISDIR(child_result.st_mode):
                    remove_directory(
                        child,
                        child_handle,
                        _PathIdentity(child, True, _identity_signature(child_result)),
                    )
                else:
                    state.api.mark_delete(child_handle)
            finally:
                try:
                    state.api.close(child_handle)
                except OSError:
                    pass

        _assert_windows_directory_current(
            directory,
            directory_handle,
            expected,
            binding=binding,
            operation=operation,
            attempts=attempts,
        )
        state.api.mark_delete(directory_handle)

    root_result = _lstat_no_follow(root)
    remove_directory(
        root,
        root_handle,
        _PathIdentity(root, True, _identity_signature(root_result)),
    )


def _remove_windows_with_quarantine(
    path: Path,
    *,
    binding: _PathBinding,
    operation: str,
    attempts: int = 0,
) -> None:
    """Quarantine one verified path before recursive Windows deletion."""

    native_state = binding.windows_state
    if _REAL_WINDOWS:
        if native_state is None:
            raise _security_error(
                operation=operation,
                path=path,
                reason=(
                    "native handle-relative Windows cleanup is unavailable; "
                    "pathname deletion is forbidden"
                ),
                attempts=attempts,
            )
        if native_state.target_handle is None:
            # The binding was made against an absent final component.  The
            # caller's boundary assertion has already rejected a new target.
            return

        if binding.quarantine_path is None:
            try:
                result = _lstat_no_follow(path)
            except FileNotFoundError as error:
                raise _security_error(
                    operation=operation,
                    path=path,
                    reason="bound Windows target disappeared before quarantine",
                    attempts=attempts,
                ) from error
            if stat.S_ISLNK(result.st_mode) or _is_reparse_point(path, result):
                raise _security_error(
                    operation=operation,
                    path=path,
                    reason=(
                        "target became a symlink or reparse point before quarantine"
                    ),
                    attempts=attempts,
                )
            if native_state.target_is_directory:
                _assert_tree_has_no_reparse_points(
                    path,
                    operation=operation,
                    root_device=binding.identities[0].signature[0],
                )
            quarantine = _new_quarantine_path(path, operation=operation)

            # This is the final race seam.  The second assertion is
            # intentional: a test or another process may replace an ancestor
            # after validation, and no native mutation is attempted then.
            binding.assert_current(operation=operation, attempts=attempts)
            _run_windows_mutation_hook(path)
            binding.assert_current(operation=operation, attempts=attempts)
            native_state.api.rename_relative(
                native_state.target_handle,
                native_state.parent_handle,
                quarantine.name,
            )
            binding.bind_quarantine(quarantine)
            if binding.quarantine_signature != binding.identities[-1].signature:
                raise _security_error(
                    operation=operation,
                    path=path,
                    reason="quarantine identity did not match the bound target",
                    attempts=attempts,
                )

        quarantine_path = binding.quarantine_path
        if quarantine_path is None:
            return
        binding.assert_current(operation=operation, attempts=attempts)
        quarantine_signature = _inspect_existing_identity(
            quarantine_path,
            operation=operation,
            attempts=attempts,
        )
        if quarantine_signature != binding.quarantine_signature:
            raise _security_error(
                operation=operation,
                path=quarantine_path,
                reason="quarantine identity changed before deletion",
                attempts=attempts,
            )
        if native_state.target_is_directory:
            _remove_windows_tree_by_handles(
                quarantine_path,
                native_state.target_handle,
                binding=binding,
                operation=operation,
                attempts=attempts,
                root_device=binding.identities[0].signature[0],
            )
        else:
            native_state.api.mark_delete(native_state.target_handle)
        native_state.deletion_marked = True
        return

    # Non-Windows tests may set _IS_WINDOWS to exercise retry behavior.  This
    # compatibility branch is never used by production Windows code because
    # _REAL_WINDOWS remains true there and path-based mutation is forbidden.
    if binding.quarantine_path is None:
        try:
            result = _lstat_no_follow(path)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(result.st_mode) or _is_reparse_point(path, result):
            raise _security_error(
                operation=operation,
                path=path,
                reason="target became a symlink or reparse point before quarantine",
                attempts=attempts,
            )
        quarantine = _new_quarantine_path(path, operation=operation)
        binding.assert_current(operation=operation, attempts=attempts)
        _run_windows_mutation_hook(path)
        binding.assert_current(operation=operation, attempts=attempts)
        # This branch is only a test simulation on non-Windows hosts; actual
        # Windows uses the handle-relative API above.
        os.rename(path, quarantine)
        binding.bind_quarantine(quarantine)
        if binding.quarantine_signature != binding.identities[-1].signature:
            raise _security_error(
                operation=operation,
                path=path,
                reason="quarantine identity did not match the bound target",
                attempts=attempts,
            )

    quarantine_path = binding.quarantine_path
    if quarantine_path is None:
        return
    quarantine_signature = _inspect_existing_identity(
        quarantine_path,
        operation=operation,
        attempts=attempts,
    )
    if quarantine_signature != binding.quarantine_signature:
        raise _security_error(
            operation=operation,
            path=quarantine_path,
            reason="quarantine identity changed before deletion",
            attempts=attempts,
        )
    try:
        quarantine_result = _lstat_no_follow(quarantine_path)
    except FileNotFoundError as error:
        raise _security_error(
            operation=operation,
            path=quarantine_path,
            reason="quarantine disappeared before deletion",
            attempts=attempts,
        ) from error
    if stat.S_ISDIR(quarantine_result.st_mode):
        _assert_tree_has_no_reparse_points(
            quarantine_path,
            operation=operation,
            root_device=binding.identities[0].signature[0],
        )
        shutil.rmtree(quarantine_path)
    else:
        os.unlink(quarantine_path)


def _remove_once(
    path: Path,
    *,
    parent_fd: Optional[int] = None,
    operation: str = "remove owned packaging path",
    binding: Optional[_PathBinding] = None,
    attempts: int = 0,
) -> None:
    """Remove one already-bound path without following its final link."""

    if _IS_WINDOWS:
        if binding is None:
            raise _security_error(
                operation=operation,
                path=path,
                reason="Windows cleanup requires an identity-bound path",
            )
        _remove_windows_with_quarantine(
            path,
            binding=binding,
            operation=operation,
            attempts=attempts,
        )
        return

    if parent_fd is not None:
        name = path.name
        try:
            result = os.lstat(name, dir_fd=parent_fd)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(result.st_mode) or _is_reparse_point(path, result):
            raise _security_error(
                operation=operation,
                path=path,
                reason="target became a symlink or reparse point during cleanup",
            )
        if stat.S_ISDIR(result.st_mode):
            if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
                raise _security_error(
                    operation=operation,
                    path=path,
                    reason="safe descriptor-based recursive removal is unavailable",
                )
            shutil.rmtree(name, dir_fd=parent_fd)
            return
        if not stat.S_ISREG(result.st_mode):
            raise OSError(errno.EINVAL, f"unsupported packaging output type: {path}")
        os.unlink(name, dir_fd=parent_fd)
        return

    try:
        result = _lstat_no_follow(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(result.st_mode) or _is_reparse_point(path, result):
        raise _security_error(
            operation=operation,
            path=path,
            reason="target became a symlink or reparse point during cleanup",
        )
    if stat.S_ISDIR(result.st_mode):
        shutil.rmtree(path)
        return
    if not stat.S_ISREG(result.st_mode):
        raise OSError(errno.EINVAL, f"unsupported packaging output type: {path}")
    os.unlink(path)


def _close_child_streams(child: object) -> None:
    """Close any standard streams exposed by a child process object."""

    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(child, stream_name, None)
        if stream is not None and not getattr(stream, "closed", False):
            stream.close()


def run_process_and_wait(
    command: Sequence[Union[str, os.PathLike[str]]], *, cwd: Path
) -> None:
    """Run a packaging child to completion and close its process handles."""

    with subprocess.Popen(command, cwd=os.fspath(cwd)) as child:
        return_code = child.wait()
        _close_child_streams(child)
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


def _ensure_child_exited(child: object, *, operation: str, path: Path) -> None:
    """Refuse cleanup while a child is alive, then close its streams."""

    try:
        return_code = child.poll()  # type: ignore[attr-defined]
        if return_code is None:
            try:
                return_code = child.wait(timeout=0)  # type: ignore[attr-defined]
            except subprocess.TimeoutExpired as error:
                diagnostic = _diagnostic(
                    operation=operation,
                    path=path,
                    attempts=0,
                    error=error,
                    child_alive=True,
                    reason="child process is still alive; cleanup refused",
                )
                raise PackagingCleanupError(diagnostic) from error
        _close_child_streams(child)
    except PackagingCleanupError:
        raise
    except (OSError, ValueError) as error:
        diagnostic = _diagnostic(
            operation=operation,
            path=path,
            attempts=0,
            error=error,
            reason="child process handle or stream could not be closed",
        )
        raise PackagingCleanupError(diagnostic) from error


def remove_owned_path(
    path: Path,
    *,
    owner_root: Path,
    operation: str,
    child: Optional[object] = None,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: tuple[float, ...] = _DEFAULT_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Remove an owned path with bounded Windows lock-race retries.

    ``owner_root`` is an explicit parent scope; the scope itself can never be
    removed.  Only Windows sharing/access-denied errors are retried, and an
    exhausted retry or any other error raises ``PackagingCleanupError`` while
    leaving the path in place.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    binding: Optional[_PathBinding] = None
    bind_attempt = 0
    while binding is None:
        bind_attempt += 1
        try:
            binding = _bind_owned_path(
                Path(path),
                Path(owner_root),
                operation=operation,
            )
        except PackagingCleanupError:
            raise
        except OSError as error:
            transient = is_transient_windows_cleanup_error(error)
            if not transient or bind_attempt == max_attempts:
                diagnostic = _diagnostic(
                    operation=operation,
                    path=_absolute_lexical_path(Path(path)),
                    attempts=bind_attempt,
                    error=error,
                    transient=transient,
                    exhausted=transient and bind_attempt == max_attempts,
                    reason=(
                        "recognized transient Windows lock persisted while "
                        "binding cleanup handles"
                        if transient and bind_attempt == max_attempts
                        else "could not bind cleanup path"
                    ),
                )
                raise PackagingCleanupError(diagnostic) from error
            if backoff_seconds:
                delay_index = min(bind_attempt - 1, len(backoff_seconds) - 1)
                sleep(backoff_seconds[delay_index])
    assert binding is not None
    target = binding.target
    if child is not None:
        try:
            _ensure_child_exited(child, operation=operation, path=target)
        except BaseException:
            binding.close()
            raise

    try:
        for attempt in range(1, max_attempts + 1):
            binding.assert_current(operation=operation, attempts=attempt)
            try:
                _remove_once(
                    target,
                    parent_fd=binding.parent_fd,
                    operation=operation,
                    binding=binding,
                    attempts=attempt,
                )
                return
            except PackagingCleanupError:
                raise
            except OSError as error:
                transient = is_transient_windows_cleanup_error(error)
                if not transient or attempt == max_attempts:
                    diagnostic = _diagnostic(
                        operation=operation,
                        path=target,
                        attempts=attempt,
                        error=error,
                        transient=transient,
                        exhausted=transient and attempt == max_attempts,
                        reason=(
                            "recognized transient Windows lock persisted"
                            if transient and attempt == max_attempts
                            else "non-retryable cleanup error"
                        ),
                    )
                    raise PackagingCleanupError(diagnostic) from error
                if backoff_seconds:
                    delay_index = min(attempt - 1, len(backoff_seconds) - 1)
                    sleep(backoff_seconds[delay_index])
    finally:
        binding.close()
