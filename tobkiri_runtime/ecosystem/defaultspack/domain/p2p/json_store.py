from __future__ import annotations

import json
import os
import secrets
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


DEFAULT_LOCK_TIMEOUT_SECONDS = 5.0
DEFAULT_LOCK_STALE_SECONDS = 30.0


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data


def save_json_object(path: Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(target)


@contextmanager
def file_lock(
    path: Path,
    *,
    lock_name: str = "json store",
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    stale_seconds: float = DEFAULT_LOCK_STALE_SECONDS,
) -> Iterator[None]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_suffix(target.suffix + ".lock")
    deadline = time.monotonic() + float(timeout_seconds)
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > float(stale_seconds):
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out acquiring {lock_name} lock: {lock_path}")
            time.sleep(0.025)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
