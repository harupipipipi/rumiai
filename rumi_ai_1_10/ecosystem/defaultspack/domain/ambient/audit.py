from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


RAW_KEY_PARTS = (
    "audio",
    "embedding",
    "sample",
    "pcm",
    "wav",
    "image",
    "frame",
    "video",
    "snapshot",
    "base64",
    "blob",
    "bytes",
    "dataurl",
    "data_url",
    "attachment",
)


class AmbientAuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _audit_path()

    def record(self, record: dict[str, Any]) -> dict[str, Any]:
        item = sanitize_for_audit(record)
        item.setdefault("created_at", _now())
        item.setdefault("privacy", {})
        if isinstance(item["privacy"], dict):
            item["privacy"].update(
                {
                    "audio_saved": False,
                    "image_saved": False,
                    "frame_saved": False,
                    "image_uploaded": False,
                }
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        return item

    def tail(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        except OSError:
            return []
        items: list[dict[str, Any]] = []
        for line in lines[-max(1, int(limit)) :]:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                items.append(sanitize_for_audit(data))
        return items


def sanitize_for_audit(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(part in lowered for part in RAW_KEY_PARTS):
                continue
            result[key_text] = sanitize_for_audit(item)
        return result
    if isinstance(value, list):
        return [sanitize_for_audit(item) for item in value[:50]]
    if isinstance(value, str):
        if value.startswith(("data:audio/", "data:image/", "data:video/")):
            return "[redacted-media-data-url]"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _audit_path() -> Path:
    configured = os.environ.get("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "ambient" / "audit.jsonl"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
