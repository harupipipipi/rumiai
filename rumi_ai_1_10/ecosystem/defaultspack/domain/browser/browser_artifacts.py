from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_artifact_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_BROWSER_ARTIFACTS_PATH")
    if override:
        return Path(override)
    return _pack_root() / "user_data" / "browser" / "artifacts.jsonl"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class BrowserArtifactStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_artifact_path()
        self._lock = threading.RLock()

    def record(self, action: str, result: dict[str, Any], *, session_id: str | None = None) -> dict[str, Any]:
        session = session_id or str(result.get("profile_id") or result.get("session_id") or "default")
        artifact = {
            "artifact_id": "brart_" + uuid.uuid4().hex,
            "session_id": session,
            "action": str(action or result.get("action") or "browser.action"),
            "created_at": _now_iso(),
            "url": result.get("url") or result.get("last_url"),
            "title": result.get("title"),
            "text": result.get("text") or result.get("summary"),
            "console": result.get("console") or result.get("console_logs") or [],
            "screenshot": self._screenshot_payload(result),
            "metadata": self._metadata(result),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(artifact, ensure_ascii=False, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return artifact

    def list(self, *, session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(500, int(limit or 100)))
        if not self.path.is_file():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        artifacts = []
        for line in lines[-limit * 2:]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if session_id and str(item.get("session_id") or "") != str(session_id):
                continue
            artifacts.append(item)
        return artifacts[-limit:][::-1]

    @staticmethod
    def _screenshot_payload(result: dict[str, Any]) -> dict[str, Any] | None:
        path = result.get("path") or result.get("screenshot_path") or result.get("model_image_path")
        data_url = result.get("data_url") or result.get("model_image")
        if not path and not data_url:
            return None
        return {
            "path": path,
            "model_image_path": result.get("model_image_path"),
            "data_url": data_url,
            "mime_type": result.get("mime_type", "image/png"),
            "image_size": result.get("image_size") or result.get("model_image_size"),
            "target_window": result.get("target_window") or result.get("selected_window"),
        }

    @staticmethod
    def _metadata(result: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "opened",
            "managed_profile",
            "persistent",
            "platform",
            "active_window",
            "selected_window",
            "target_app",
            "requires_approval",
            "approval_required",
            "reason",
            "launch",
        )
        return {key: result.get(key) for key in keys if key in result}
