from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any


_APPROVAL_TTL_SECONDS = 300
_SESSION_TTL_SECONDS = 3600
_SECRET_KEY_RE = re.compile(
    r"(^|[_-])(api[_-]?key|authorization|bearer|client[_-]?secret|cookie|credential|password|private[_-]?key|refresh[_-]?token|secret|token)([_-]|$)",
    re.IGNORECASE,
)

_LOW_RISK_ACTIONS = {
    "browser.session",
    "browser.profile.list",
    "browser.profiles.list",
    "browser.session.health",
    "browser.session.list",
    "browser.tab.list",
    "browser.cookies.list",
    "computer.health",
    "computer.permissions",
    "computer.displays.list",
    "computer.active_window",
    "computer.windows.list",
    "computer.wait",
}

_HIGH_RISK_ACTIONS = {
    "browser.profile.delete",
    "computer.app.open",
    "computer.clipboard.write",
}

_DANGEROUS_HOTKEYS = {
    "alt+f4",
    "cmd+delete",
    "cmd+q",
    "cmd+w",
    "command+delete",
    "command+q",
    "command+w",
    "ctrl+w",
    "meta+delete",
    "meta+q",
    "meta+w",
    "shift+cmd+delete",
    "shift+command+delete",
}


def approval_store_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_APPROVAL_STORE_PATH", "").strip()
    if override:
        return Path(override)
    pack_root = Path(__file__).resolve().parents[2]
    return pack_root / "user_data" / "shared" / "approvals" / "tool_approvals.json"


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                redacted[key_text] = "[redacted]" if item not in (None, "") else item
            else:
                redacted[key_text] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def classify_approval_risk(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    action = str(action or "")
    payload = payload if isinstance(payload, dict) else {}
    if bool(payload.get("dry_run")):
        return {"risk_level": "low", "approval_required": False, "reason": "dry_run"}
    if action in _LOW_RISK_ACTIONS:
        return {"risk_level": "low", "approval_required": False, "reason": "read_only_action"}
    if action == "computer.hotkey":
        combo = _canonical_hotkey(payload)
        if combo in _DANGEROUS_HOTKEYS:
            return {"risk_level": "high", "approval_required": True, "reason": "dangerous_hotkey"}
        return {"risk_level": "medium", "approval_required": True, "reason": "hotkey"}
    if action in _HIGH_RISK_ACTIONS:
        return {"risk_level": "high", "approval_required": True, "reason": "high_risk_action"}
    if action.startswith("computer.") or action.startswith("browser."):
        return {"risk_level": "medium", "approval_required": True, "reason": "state_changing_action"}
    return {"risk_level": "medium", "approval_required": True, "reason": "tool_action"}


def _canonical_hotkey(payload: dict[str, Any]) -> str:
    raw = payload.get("combo") or payload.get("hotkey") or payload.get("key") or ""
    parts: list[str]
    if isinstance(payload.get("keys"), list):
        parts = [str(part).strip().lower() for part in payload["keys"]]
    else:
        parts = [part.strip().lower() for part in re.split(r"[+\s]+", str(raw)) if part.strip()]
    aliases = {
        "control": "ctrl",
        "ctl": "ctrl",
        "option": "alt",
        "command": "cmd",
        "meta": "cmd",
        "return": "enter",
        "escape": "esc",
    }
    normalized = [aliases.get(part, part) for part in parts]
    modifiers = [part for part in ("ctrl", "alt", "shift", "cmd") if part in normalized]
    keys = [part for part in normalized if part not in {"ctrl", "alt", "shift", "cmd"}]
    return "+".join(modifiers + keys)


class ApprovalStore:
    """JSON-backed approval store with server-issued approval ids and tokens."""

    def __init__(self, path: Path | None = None, *, now=None) -> None:
        self.path = Path(path) if path is not None else approval_store_path()
        self._now = now or time.time

    def request(
        self,
        action: str,
        payload: dict[str, Any] | None,
        *,
        risk_level: str = "medium",
        reason: str = "",
        ttl_seconds: int = _APPROVAL_TTL_SECONDS,
        issue_legacy_once_token: bool = False,
    ) -> dict[str, Any]:
        payload = copy.deepcopy(payload if isinstance(payload, dict) else {})
        data = self._load()
        approval_id = "appr_" + secrets.token_urlsafe(16)
        record: dict[str, Any] = {
            "id": approval_id,
            "status": "pending",
            "action": str(action),
            "risk_level": str(risk_level or "medium"),
            "reason": str(reason or ""),
            "payload": redact_secrets(payload),
            "payload_fingerprint": self._fingerprint(action, payload),
            "requested_at": self._iso(),
            "expires_at": self._now() + int(ttl_seconds or _APPROVAL_TTL_SECONDS),
            "approval_mode": None,
        }
        response: dict[str, Any] = {
            "approval_id": approval_id,
            "approval_expires_in_seconds": int(ttl_seconds or _APPROVAL_TTL_SECONDS),
            "risk_level": record["risk_level"],
            "status": "pending",
            "payload": record["payload"],
        }
        if issue_legacy_once_token:
            token = self._set_token(record, mode="once", ttl_seconds=ttl_seconds, status="approved")
            record["legacy_token"] = True
            response["approval_token"] = token
            response["status"] = "approved"
        data["requests"][approval_id] = record
        self._save(data)
        return response

    def approve_once(self, approval_id: str, *, ttl_seconds: int = _APPROVAL_TTL_SECONDS) -> dict[str, Any]:
        return self._approve(approval_id, mode="once", ttl_seconds=ttl_seconds)

    def approve_session(
        self,
        approval_id: str,
        *,
        session_id: str = "",
        ttl_seconds: int = _SESSION_TTL_SECONDS,
    ) -> dict[str, Any]:
        return self._approve(approval_id, mode="session", ttl_seconds=ttl_seconds, session_id=session_id)

    def deny(self, approval_id: str, *, reason: str = "") -> dict[str, Any]:
        data = self._load()
        record = data["requests"].get(str(approval_id))
        if not isinstance(record, dict):
            return {"ok": False, "error": "approval_not_found"}
        record["status"] = "denied"
        record["denied_at"] = self._iso()
        record["denial_reason"] = str(reason or "")
        record.pop("token_hash", None)
        self._save(data)
        return {"ok": True, "approval": self._public_record(record)}

    def consume(
        self,
        *,
        approval_id: str = "",
        approval_token: str = "",
        action: str,
        payload: dict[str, Any] | None,
        allow_legacy_token: bool = False,
        session_id: str = "",
    ) -> bool:
        token = str(approval_token or "")
        if not token:
            return False
        data = self._load()
        records = data["requests"]
        candidates: list[dict[str, Any]] = []
        if approval_id and isinstance(records.get(str(approval_id)), dict):
            candidates.append(records[str(approval_id)])
        else:
            candidates = [record for record in records.values() if isinstance(record, dict)]
        token_hash = self._hash_token(token)
        now = self._now()
        expected = self._fingerprint(action, payload if isinstance(payload, dict) else {})
        changed = False
        for record in candidates:
            if float(record.get("expires_at") or 0) < now:
                record["status"] = "expired"
                changed = True
                continue
            if record.get("status") != "approved":
                continue
            if record.get("token_hash") != token_hash:
                continue
            if record.get("action") != action or record.get("payload_fingerprint") != expected:
                continue
            if bool(record.get("legacy_token")) and not allow_legacy_token:
                continue
            mode = str(record.get("approval_mode") or "once")
            if mode == "session":
                if record.get("session_id") and session_id and record.get("session_id") != session_id:
                    continue
                if float(record.get("approved_until") or 0) < now:
                    record["status"] = "expired"
                    changed = True
                    continue
                if changed:
                    self._save(data)
                return True
            record["status"] = "consumed"
            record["consumed_at"] = self._iso()
            self._save(data)
            return True
        if changed:
            self._save(data)
        return False

    def list(self, *, include_expired: bool = False, status: str = "") -> list[dict[str, Any]]:
        data = self._load()
        now = self._now()
        records = []
        changed = False
        for record in data["requests"].values():
            if not isinstance(record, dict):
                continue
            if float(record.get("expires_at") or 0) < now and record.get("status") in {"pending", "approved"}:
                record["status"] = "expired"
                changed = True
            if not include_expired and record.get("status") == "expired":
                continue
            if status and record.get("status") != status:
                continue
            records.append(self._public_record(record))
        if changed:
            self._save(data)
        return sorted(records, key=lambda item: str(item.get("requested_at") or ""), reverse=True)

    def get(self, approval_id: str) -> dict[str, Any] | None:
        record = self._load()["requests"].get(str(approval_id))
        if not isinstance(record, dict):
            return None
        return self._public_record(record)

    def _approve(
        self,
        approval_id: str,
        *,
        mode: str,
        ttl_seconds: int,
        session_id: str = "",
    ) -> dict[str, Any]:
        data = self._load()
        record = data["requests"].get(str(approval_id))
        if not isinstance(record, dict):
            return {"ok": False, "error": "approval_not_found"}
        if record.get("status") == "denied":
            return {"ok": False, "error": "approval_denied", "approval": self._public_record(record)}
        if float(record.get("expires_at") or 0) < self._now():
            record["status"] = "expired"
            self._save(data)
            return {"ok": False, "error": "approval_expired", "approval": self._public_record(record)}
        token = self._set_token(record, mode=mode, ttl_seconds=ttl_seconds, status="approved", session_id=session_id)
        self._save(data)
        return {
            "ok": True,
            "approval_id": record["id"],
            "approval_token": token,
            "approval_mode": mode,
            "approval_expires_in_seconds": int(ttl_seconds),
            "approval": self._public_record(record),
        }

    def _set_token(
        self,
        record: dict[str, Any],
        *,
        mode: str,
        ttl_seconds: int,
        status: str,
        session_id: str = "",
    ) -> str:
        token = secrets.token_urlsafe(32)
        now = self._now()
        record["status"] = status
        record["approval_mode"] = mode
        record["approved_at"] = self._iso()
        record["approved_until"] = now + int(ttl_seconds)
        record["token_hash"] = self._hash_token(token)
        if session_id:
            record["session_id"] = str(session_id)
        return token

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        requests = payload.get("requests")
        if not isinstance(requests, dict):
            requests = {}
        return {"version": 1, "requests": requests}

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _public_record(self, record: dict[str, Any]) -> dict[str, Any]:
        public = {key: value for key, value in record.items() if key not in {"token_hash"}}
        if record.get("id"):
            public.setdefault("approval_id", record.get("id"))
        if record.get("payload"):
            public.setdefault("payload_redacted", record.get("payload"))
        public["expired"] = float(record.get("expires_at") or 0) < self._now()
        public["expires_at_epoch"] = record.get("expires_at")
        public["has_token"] = bool(record.get("token_hash"))
        return public

    def _fingerprint(self, action: str, payload: dict[str, Any]) -> str:
        canonical = json.dumps({"action": action, "payload": payload}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _iso(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._now()))
