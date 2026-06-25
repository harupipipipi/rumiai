from __future__ import annotations

import json
import os
import threading
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
        self._lock = threading.RLock()

    def read(self) -> dict[str, Any]:
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return {}
            return data if isinstance(data, dict) else {}

    def write(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            tmp.replace(self.path)

    def update(self, callback):
        with self._lock:
            data = self.read()
            next_data, result = callback(data)
            self.write(next_data)
            return result
