from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any


class ShareStore:
    def __init__(self, root: Path | None = None) -> None:
        pack_root = Path(__file__).resolve().parents[2]
        self._root = root or pack_root / "user_data" / "share_links"
        self._root.mkdir(parents=True, exist_ok=True)

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_type = str(payload.get("target_type") or "content")
        token = secrets.token_urlsafe(18)
        record = {
            "token": token,
            "target_type": target_type,
            "target_id": payload.get("target_id"),
            "title": payload.get("title") or target_type,
            "content": payload.get("content"),
            "visibility": payload.get("visibility") or "local",
            "permissions": payload.get("permissions") or {"read": True},
            "expires_at": payload.get("expires_at"),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "revoked": False,
        }
        self._path(token).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        record["share_url"] = f"/api/share/{token}"
        return record

    def get(self, token: str) -> dict[str, Any] | None:
        path = self._path(token)
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("revoked"):
            return None
        expires_at = record.get("expires_at")
        if expires_at and str(expires_at) < time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()):
            return None
        record["share_url"] = f"/api/share/{token}"
        return record

    def list(self) -> list[dict[str, Any]]:
        records = []
        for path in sorted(self._root.glob("share_*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            record["share_url"] = f"/api/share/{record.get('token', '')}"
            records.append(record)
        return records

    def revoke(self, token: str) -> bool:
        path = self._path(token)
        if not path.exists():
            return False
        record = json.loads(path.read_text(encoding="utf-8"))
        record["revoked"] = True
        record["revoked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return True

    def _path(self, token: str) -> Path:
        safe = "".join(ch for ch in token if ch.isalnum() or ch in "-_")
        return self._root / f"share_{safe}.json"
