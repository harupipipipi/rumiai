from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from .context import adaptive_store_root, clean_profile_id


class AdaptiveStore:
    def __init__(self, profile_id: str, root: Path | None = None) -> None:
        self.profile_id = clean_profile_id(profile_id)
        self.root = Path(root).resolve() if root is not None else adaptive_store_root(self.profile_id)

    def read_json(self, relative_path: str, default: Any) -> Any:
        path = self._path(relative_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default
        return data

    def write_json(self, relative_path: str, payload: Any) -> Any:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
        return payload

    def update_json(self, relative_path: str, default: Any, update: Callable[[Any], Any]) -> Any:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd, lock_path = self._acquire_lock(path)
        try:
            current = self.read_json(relative_path, default)
            next_payload = update(current)
            return self.write_json(relative_path, next_payload)
        finally:
            self._release_lock(lock_fd, lock_path)

    def append_jsonl(self, relative_path: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd, lock_path = self._acquire_lock(path)
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        finally:
            self._release_lock(lock_fd, lock_path)
        return payload

    def append_jsonl_once(
        self,
        relative_path: str,
        payload: dict[str, Any],
        *,
        key: str,
        value: Any,
    ) -> tuple[dict[str, Any], bool]:
        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd, lock_path = self._acquire_lock(path)
        try:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (FileNotFoundError, OSError):
                lines = []
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    existing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(existing, dict) and existing.get(key) == value:
                    return existing, True
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            return payload, False
        finally:
            self._release_lock(lock_fd, lock_path)

    def read_jsonl(self, relative_path: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        path = self._path(relative_path)
        rows: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError):
            return []
        if limit is not None and limit >= 0:
            lines = lines[-limit:]
        for line in lines:
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
        return rows

    def _path(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        root = self.root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("adaptive store path escaped profile root") from exc
        return candidate

    def _acquire_lock(self, path: Path, *, timeout_seconds: float = 5.0, stale_seconds: float = 30.0) -> tuple[int, Path]:
        lock_path = path.with_suffix(path.suffix + ".lock")
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
                return fd, lock_path
            except (FileExistsError, PermissionError):
                try:
                    age = time.time() - lock_path.stat().st_mtime
                    if age > stale_seconds:
                        try:
                            lock_path.unlink()
                        except (FileNotFoundError, PermissionError):
                            pass
                        continue
                except (FileNotFoundError, PermissionError):
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for adaptive store lock: {lock_path.name}")
                time.sleep(0.025)

    @staticmethod
    def _release_lock(lock_fd: int, lock_path: Path) -> None:
        os.close(lock_fd)
        deadline = time.monotonic() + 0.5
        while True:
            try:
                lock_path.unlink()
                return
            except FileNotFoundError:
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    return
                time.sleep(0.01)
