"""Signed one-shot approval challenge storage."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..compat import safe_chmod
from ..hmac_key_manager import generate_or_load_signing_key
from ..paths import USER_DATA_DIR
from .models import AuthorityRequest


DEFAULT_CHALLENGE_TTL_SECONDS = 120


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_ts(value: datetime | None = None) -> str:
    return (value or _now_utc()).isoformat().replace("+00:00", "Z")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_id(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovalChallenge:
    challenge_id: str
    request_id: str
    profile_id: str
    device_id: str
    token_id: str
    permission_id: str
    resource_hash: str
    decision: str
    scope: str
    nonce: str
    issued_at: str
    expires_at: str
    payload_hash: str
    consumed: bool = False
    consumed_at: str | None = None

    def payload_for_signature(self) -> dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "request_id": self.request_id,
            "profile_id": self.profile_id,
            "device_id": self.device_id,
            "token_id": self.token_id,
            "permission_id": self.permission_id,
            "resource_hash": self.resource_hash,
            "decision": self.decision,
            "scope": self.scope,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.payload_for_signature(),
            "payload_hash": self.payload_hash,
            "consumed": self.consumed,
            "consumed_at": self.consumed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalChallenge":
        return cls(
            challenge_id=str(data.get("challenge_id") or ""),
            request_id=str(data.get("request_id") or ""),
            profile_id=str(data.get("profile_id") or ""),
            device_id=str(data.get("device_id") or ""),
            token_id=str(data.get("token_id") or ""),
            permission_id=str(data.get("permission_id") or ""),
            resource_hash=str(data.get("resource_hash") or ""),
            decision=str(data.get("decision") or ""),
            scope=str(data.get("scope") or ""),
            nonce=str(data.get("nonce") or ""),
            issued_at=str(data.get("issued_at") or ""),
            expires_at=str(data.get("expires_at") or ""),
            payload_hash=str(data.get("payload_hash") or ""),
            consumed=bool(data.get("consumed")),
            consumed_at=str(data.get("consumed_at") or "") or None,
        )


class ApprovalChallengeStore:
    def __init__(
        self,
        base_dir: str | Path | None = None,
        *,
        secret_key: str | bytes | None = None,
        hmac_key_manager: Any = None,
    ) -> None:
        self._base_dir = Path(base_dir) if base_dir else USER_DATA_DIR / "authority" / "approval_challenges"
        if isinstance(secret_key, bytes):
            self._secret_key = secret_key
        elif secret_key:
            self._secret_key = str(secret_key).encode("utf-8")
        elif hmac_key_manager is not None:
            try:
                self._secret_key = str(hmac_key_manager.get_active_key()).encode("utf-8")
            except Exception:
                self._secret_key = generate_or_load_signing_key(
                    USER_DATA_DIR / "permissions" / ".authority_challenge_key"
                )
        else:
            self._secret_key = generate_or_load_signing_key(
                USER_DATA_DIR / "permissions" / ".authority_challenge_key"
            )
        self._lock = threading.RLock()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def issue_challenge(
        self,
        *,
        request: AuthorityRequest,
        profile_id: str,
        device_id: str,
        token_id: str,
        resource_hash: str,
        decision: str,
        scope: str,
        expires_in_seconds: int | None = DEFAULT_CHALLENGE_TTL_SECONDS,
    ) -> ApprovalChallenge:
        now = _now_utc()
        ttl = max(15, min(int(expires_in_seconds or DEFAULT_CHALLENGE_TTL_SECONDS), 300))
        payload = {
            "challenge_id": "ach_" + secrets.token_urlsafe(16),
            "request_id": request.request_id,
            "profile_id": str(profile_id or "").strip(),
            "device_id": str(device_id or "").strip(),
            "token_id": str(token_id or "").strip(),
            "permission_id": request.permission_id,
            "resource_hash": resource_hash,
            "decision": str(decision or "").strip().lower(),
            "scope": str(scope or "").strip().lower(),
            "nonce": secrets.token_urlsafe(24),
            "issued_at": _now_ts(now),
            "expires_at": _now_ts(now + timedelta(seconds=ttl)),
        }
        payload_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        challenge = ApprovalChallenge.from_dict({**payload, "payload_hash": payload_hash})
        with self._lock:
            self._write_challenge(challenge)
        return challenge

    def get_challenge(self, challenge_id: str) -> ApprovalChallenge | None:
        with self._lock:
            data = self._read_payload(self._path(challenge_id))
        return ApprovalChallenge.from_dict(data) if data else None

    def challenge_expired(self, challenge: ApprovalChallenge) -> bool:
        expires_at = _parse_ts(challenge.expires_at)
        return bool(expires_at is None or expires_at <= _now_utc())

    def consume_challenge(self, *, challenge_id: str, payload_hash: str) -> bool:
        with self._lock:
            path = self._path(challenge_id)
            data = self._read_payload(path)
            if not data:
                return False
            challenge = ApprovalChallenge.from_dict(data)
            if challenge.consumed or self.challenge_expired(challenge):
                return False
            if not hmac.compare_digest(challenge.payload_hash, str(payload_hash or "")):
                return False
            data["consumed"] = True
            data["consumed_at"] = _now_ts()
            self._write_payload(path, data)
            return True

    def _path(self, challenge_id: str) -> Path:
        return self._base_dir / f"{_safe_id(challenge_id)}.json"

    def _signature(self, payload: dict[str, Any]) -> str:
        filtered = {key: value for key, value in payload.items() if key != "_hmac_signature"}
        return hmac.new(self._secret_key, _canonical_json(filtered).encode("utf-8"), hashlib.sha256).hexdigest()

    def _write_challenge(self, challenge: ApprovalChallenge) -> None:
        self._write_payload(self._path(challenge.challenge_id), challenge.to_dict())

    def _write_payload(self, path: Path, payload: dict[str, Any]) -> None:
        data = dict(payload)
        data["_hmac_signature"] = self._signature(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.stem}.", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            try:
                safe_chmod(tmp_path, 0o600)
            except (OSError, AttributeError):
                pass
            Path(tmp_path).replace(path)
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass

    def _read_payload(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        signature = str(data.get("_hmac_signature") or "")
        payload = {key: value for key, value in data.items() if key != "_hmac_signature"}
        if not signature or not hmac.compare_digest(signature, self._signature(payload)):
            return None
        return payload
