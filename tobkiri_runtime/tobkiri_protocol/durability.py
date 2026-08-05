"""Cross-platform durable atomic file replacement primitives."""

from __future__ import annotations

import ctypes
import os
import secrets
from pathlib import Path
from typing import Any


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Durably replace ``path`` with ``data`` or propagate the exact failure.

    The temporary file is created beside the destination so ``os.replace`` is
    a same-filesystem atomic rename. File contents are flushed before the
    rename and parent-directory metadata is flushed after it. A failure after
    replacement is deliberately reported: the bytes are present, but their
    durability was not established.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        flush_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def flush_directory(path: Path) -> None:
    """Flush directory metadata using the platform's native directory handle."""

    if os.name == "nt":
        _flush_windows_directory(path)
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _flush_windows_directory(path: Path, *, kernel32: Any | None = None) -> None:
    """Flush a Windows directory opened with backup-semantics support.

    ``os.open`` routes through the Microsoft C runtime, which rejects directory
    paths. CreateFileW is the documented Win32 route for obtaining a directory
    handle; FILE_FLAG_BACKUP_SEMANTICS is required for that use.
    """

    native = kernel32
    if native is None:
        win_dll: Any = getattr(ctypes, "WinDLL")
        native = win_dll("kernel32", use_last_error=True)
        native.CreateFileW.argtypes = (
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        )
        native.CreateFileW.restype = ctypes.c_void_p
        native.FlushFileBuffers.argtypes = (ctypes.c_void_p,)
        native.FlushFileBuffers.restype = ctypes.c_int
        native.CloseHandle.argtypes = (ctypes.c_void_p,)
        native.CloseHandle.restype = ctypes.c_int

    generic_read = 0x80000000
    generic_write = 0x40000000
    share_read_write_delete = 0x00000001 | 0x00000002 | 0x00000004
    open_existing = 3
    file_flag_backup_semantics = 0x02000000
    handle = native.CreateFileW(
        str(path),
        generic_read | generic_write,
        share_read_write_delete,
        None,
        open_existing,
        file_flag_backup_semantics,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        raise _windows_error("CreateFileW")

    flush_error: OSError | None = None
    if not native.FlushFileBuffers(handle):
        flush_error = _windows_error("FlushFileBuffers")
    close_succeeded = native.CloseHandle(handle)
    if flush_error is not None:
        raise flush_error
    if not close_succeeded:
        raise _windows_error("CloseHandle")


def _windows_error(operation: str) -> OSError:
    """Build the native Windows error, including in portable adapter tests."""

    error_code = getattr(ctypes, "get_last_error", lambda: 0)()
    win_error = getattr(ctypes, "WinError", None)
    if win_error is not None:
        return OSError(f"{operation} failed: {win_error(error_code)}")
    return OSError(error_code, f"{operation} failed with Windows error {error_code}")
