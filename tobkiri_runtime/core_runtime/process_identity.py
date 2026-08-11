"""Fail-closed process-start identity evidence for process-owned stores."""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from tobkiri_protocol.canonical import canonical_digest


@dataclass(frozen=True)
class ProcessIdentityEvidence:
    """Explicit process-liveness evidence that never conflates unknown with dead."""

    state: Literal["live", "dead", "unknown"]
    identity: str = ""

    def __post_init__(self) -> None:
        if self.state == "live" and not self.identity:
            raise ValueError("live process evidence requires an identity")
        if self.state != "live" and self.identity:
            raise ValueError("non-live process evidence cannot carry an identity")


class WindowsProcessAPI(Protocol):
    """Minimal WinAPI adapter used to obtain a process creation FILETIME."""

    def open_process(self, process_id: int) -> int | None:
        """Open a query-only handle, distinguishing absence from API failure."""

    def process_creation_time(self, handle: int) -> int | None:
        """Return the stable creation FILETIME ticks for an opened process."""

    def close_handle(self, handle: int) -> None:
        """Close an opened process handle or raise on failure."""


class _Kernel32ProcessAPI:
    """ctypes-backed Windows process creation-time adapter."""

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class FileTime(ctypes.Structure):
            _fields_ = [
                ("low", wintypes.DWORD),
                ("high", wintypes.DWORD),
            ]

        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            raise OSError("WinDLL is unavailable")
        kernel32 = win_dll("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        self._ctypes = ctypes
        self._kernel32 = kernel32
        self._file_time = FileTime
        self._get_last_error = getattr(ctypes, "get_last_error")

    def open_process(self, process_id: int) -> int | None:
        """Open a process with the least privilege needed for creation time."""

        handle = self._kernel32.OpenProcess(
            self._PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            process_id,
        )
        if handle:
            return int(handle)
        error_code = int(self._get_last_error())
        if error_code in {87, 1168}:
            raise ProcessLookupError(error_code, "Windows process does not exist")
        if error_code == 5:
            raise PermissionError(error_code, "Windows process query was denied")
        raise OSError(error_code, "OpenProcess failed")

    def process_creation_time(self, handle: int) -> int | None:
        """Read one process creation FILETIME without using a wall clock."""

        creation = self._file_time()
        exit_time = self._file_time()
        kernel_time = self._file_time()
        user_time = self._file_time()
        if not self._kernel32.GetProcessTimes(
            handle,
            self._ctypes.byref(creation),
            self._ctypes.byref(exit_time),
            self._ctypes.byref(kernel_time),
            self._ctypes.byref(user_time),
        ):
            return None
        return (int(creation.high) << 32) | int(creation.low)

    def close_handle(self, handle: int) -> None:
        """Close a process handle and surface close failures fail-closed."""

        if not self._kernel32.CloseHandle(handle):
            raise OSError("CloseHandle failed")


@lru_cache(maxsize=1)
def _load_windows_process_api() -> WindowsProcessAPI | None:
    try:
        return _Kernel32ProcessAPI()
    except (AttributeError, ImportError, OSError):
        return None


def _windows_current_process_identity(process_id: int) -> ProcessIdentityEvidence:
    """Return any Windows PID's creation FILETIME, closing every handle."""
    api = _load_windows_process_api()
    if api is None:
        return ProcessIdentityEvidence("unknown")
    handle: int | None = None
    evidence = ProcessIdentityEvidence("unknown")
    try:
        handle = api.open_process(process_id)
        if handle is None:
            return evidence
        creation_time = api.process_creation_time(handle)
        if creation_time is not None:
            evidence = ProcessIdentityEvidence(
                "live",
                f"windows:{process_id}:{creation_time:016x}",
            )
    except ProcessLookupError:
        evidence = ProcessIdentityEvidence("dead")
    except (OSError, TypeError, ValueError):
        evidence = ProcessIdentityEvidence("unknown")
    finally:
        if handle is not None:
            try:
                api.close_handle(handle)
            except (OSError, TypeError, ValueError):
                evidence = ProcessIdentityEvidence("unknown")
    return evidence


def _is_windows() -> bool:
    return os.name == "nt"


def process_start_identity(process_id: int) -> ProcessIdentityEvidence:
    """Return explicit live, dead, or unavailable PID-start evidence."""

    if process_id <= 0:
        return ProcessIdentityEvidence("unknown")
    if _is_windows():
        return _windows_current_process_identity(process_id)
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return ProcessIdentityEvidence("dead")
    except (PermissionError, OSError):
        # A denied or unsupported existence probe is not evidence of death.
        pass

    linux_stat = Path(f"/proc/{process_id}/stat")
    try:
        if linux_stat.exists():
            fields = linux_stat.read_text(encoding="ascii").rsplit(")", 1)[1].split()
            return ProcessIdentityEvidence("live", f"linux:{fields[19]}")
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(process_id)],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ProcessIdentityEvidence("unknown")
        return ProcessIdentityEvidence(
            "live", canonical_digest({"process_start": result.stdout.strip()})
        )
    except FileNotFoundError:
        return ProcessIdentityEvidence("unknown")
    except (IndexError, OSError, subprocess.SubprocessError):
        return ProcessIdentityEvidence("unknown")
