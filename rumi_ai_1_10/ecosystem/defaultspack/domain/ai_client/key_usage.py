from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


class KeyUsageTracker:
    def __init__(self, root: Path | None = None) -> None:
        pack_root = root or _pack_root()
        override = os.environ.get("RUMI_DEFAULTSPACK_API_KEY_USAGE_PATH", "").strip()
        self.path = Path(override) if override else pack_root / "user_data" / "shared" / "api_keys" / "usage.json"

    def record(self, key_id: str, *, tokens: int = 0, cost_usd: float = 0.0, requests: int = 1) -> dict[str, Any]:
        data = self._read()
        item = data.setdefault(key_id, {"requests": 0, "tokens": 0, "cost_usd": 0.0, "events": []})
        item["requests"] = int(item.get("requests") or 0) + int(requests)
        item["tokens"] = int(item.get("tokens") or 0) + int(tokens)
        item["cost_usd"] = float(item.get("cost_usd") or 0.0) + float(cost_usd)
        item.setdefault("events", []).append({"ts": time.time(), "requests": requests, "tokens": tokens, "cost_usd": cost_usd})
        self._write(data)
        return self.get(key_id)

    def get(self, key_id: str) -> dict[str, Any]:
        return self._read().get(key_id, {"requests": 0, "tokens": 0, "cost_usd": 0.0, "events": []})

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
