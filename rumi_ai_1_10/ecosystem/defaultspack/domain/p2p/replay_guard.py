from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .settings import default_store_path


def _now_ms() -> int:
    return int(time.time() * 1000)


def _replay_file(store_path: Path | None = None) -> Path:
    root = Path(store_path).expanduser() if store_path is not None else default_store_path()
    if root.name == "replay.json":
        return root
    return root / "replay.json"


class ReplayGuard:
    def __init__(self, path: Path | None = None, *, ttl_seconds: int = 600) -> None:
        self.path = _replay_file(path)
        self.ttl_seconds = max(1, int(ttl_seconds or 600))
        self._data = self._load()

    def check_and_record(
        self,
        *,
        sender_id: str,
        message_id: str,
        nonce: str,
        current_time_ms: int | None = None,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        sender = str(sender_id or "").strip()
        message = str(message_id or "").strip()
        nonce_value = str(nonce or "").strip()
        if not sender or not message or not nonce_value:
            return {"ok": False, "reason": "sender_id, message_id, and nonce are required", "code": "REPLAY_INPUT_INVALID"}
        now = int(current_time_ms if current_time_ms is not None else _now_ms())
        seen = self._seen()
        self._cleanup(seen, now)
        message_key = f"sender:{sender}:message:{message}"
        nonce_key = f"sender:{sender}:nonce:{nonce_value}"
        if message_key in seen:
            return {"ok": False, "reason": "message_id replay detected", "code": "REPLAY_DETECTED"}
        if nonce_key in seen:
            return {"ok": False, "reason": "nonce replay detected", "code": "REPLAY_DETECTED"}
        ttl = max(1, int(ttl_seconds or self.ttl_seconds))
        expires_at = now + ttl * 1000
        seen[message_key] = expires_at
        seen[nonce_key] = expires_at
        self._save(seen)
        return {"ok": True, "reason": "", "code": ""}

    def _seen(self) -> dict[str, int]:
        raw = self._data.setdefault("seen", {})
        if not isinstance(raw, dict):
            raw = {}
            self._data["seen"] = raw
        cleaned: dict[str, int] = {}
        for key, value in raw.items():
            try:
                cleaned[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return cleaned

    def _cleanup(self, seen: dict[str, int], now: int) -> None:
        for key, expires_at in list(seen.items()):
            if int(expires_at) <= now:
                seen.pop(key, None)

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("schema_version", 1)
        data.setdefault("seen", {})
        return data

    def _save(self, seen: dict[str, int]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data["schema_version"] = 1
        self._data["updated_at"] = _now_ms()
        self._data["seen"] = dict(seen)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
