from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def default_continuity_dir() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_CONTINUITY_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "continuity"


class JsonFileStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")
        self._lock = threading.RLock()

    def read(self) -> dict[str, Any]:
        with self._lock:
            with self._file_lock():
                return self._read_unlocked()

    def write(self, data: dict[str, Any]) -> None:
        with self._lock:
            with self._file_lock():
                self._write_unlocked(data)

    def update(self, callback):
        with self._lock:
            with self._file_lock():
                data = self._read_unlocked()
                next_data, result = callback(data)
                self._write_unlocked(next_data)
                return result

    @contextmanager
    def _file_lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            _lock_file_handle(handle)
            try:
                yield
            finally:
                _unlock_file_handle(handle)

    def _read_unlocked(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(self.path)


def _lock_file_handle(handle) -> None:
    if os.name == "nt":
        _windows_lock(handle)
        return
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except (ImportError, OSError):
        return


def _unlock_file_handle(handle) -> None:
    if os.name == "nt":
        _windows_unlock(handle)
        return
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except (ImportError, OSError):
        return


def _windows_lock(handle) -> None:
    try:
        import msvcrt

        _ensure_lock_byte(handle)
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    except (ImportError, OSError):
        return


def _windows_unlock(handle) -> None:
    try:
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except (ImportError, OSError):
        return


def _ensure_lock_byte(handle) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
