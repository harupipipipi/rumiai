from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ShareStore:
    def __init__(self, root: Path | None = None, *, chat_store=None, environ=None) -> None:
        pack_root = Path(__file__).resolve().parents[2]
        environment = environ if environ is not None else __import__("os").environ
        configured_root = environment.get("RUMI_DEFAULTSPACK_SHARE_STORE_PATH")
        self._root = root or (Path(configured_root) if configured_root else pack_root / "user_data" / "share_links")
        self._root.mkdir(parents=True, exist_ok=True)
        self._chat_store = chat_store
        self._environ = environment

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_type = str(payload.get("target_type") or "content")
        token = secrets.token_urlsafe(18)
        visibility = str(payload.get("visibility") or "local").strip().lower()
        content = payload.get("content")
        if target_type == "conversation":
            from domain.share.conversation_bundle import build_conversation_share_bundle

            content = build_conversation_share_bundle(
                str(payload.get("target_id") or ""), store=self._chat_store, share_token=token,
                visibility=visibility, expires_at=payload.get("expires_at"),
            )
        record = {
            "token": token,
            "target_type": target_type,
            "target_id": payload.get("target_id"),
            "title": payload.get("title") or target_type,
            "content": content,
            "visibility": visibility,
            "permissions": payload.get("permissions") or {"read": True, "import": target_type == "conversation", "continue": target_type == "conversation"},
            "expires_at": payload.get("expires_at"),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "revoked": False,
        }
        self._add_urls(record)
        if str(record.get("share_url") or "").startswith("https://"):
            record["public_share_url"] = record["share_url"]
        self._path(token).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def get(self, token: str) -> dict[str, Any] | None:
        path = self._path(token)
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("revoked"):
            return None
        expires_at = record.get("expires_at")
        if expires_at and self._is_expired(expires_at):
            return None
        self._add_urls(record)
        return record

    def list(self) -> list[dict[str, Any]]:
        records = []
        for path in sorted(self._root.glob("share_*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            self._add_urls(record)
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

    def _add_urls(self, record: dict[str, Any]) -> None:
        token = str(record.get("token") or "")
        local_url = f"/share/{token}"
        record["api_url"] = f"/api/share/{token}"
        record["share_url"] = local_url
        if record.get("visibility") in {"tunnel", "public", "cloudflare"}:
            public_url = str(record.get("public_share_url") or "").strip()
            if public_url:
                record["share_url"] = public_url
                return
            hostname = str(self._environ.get("RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME") or "").strip()
            hostname = hostname.removeprefix("https://").removeprefix("http://").strip("/")
            if not hostname or any(ch in hostname for ch in "?#@ "):
                raise ValueError("Cloudflare Tunnel hostname is not configured")
            record["share_url"] = f"https://{hostname}/share/{token}"

    @staticmethod
    def _is_expired(value: Any) -> bool:
        try:
            if isinstance(value, (int, float)):
                timestamp = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
                return timestamp <= time.time()
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp() <= time.time()
        except (TypeError, ValueError):
            return True
