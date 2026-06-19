from __future__ import annotations

import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .peer_store import PeerRecord, PeerStore, generate_shared_secret
from .settings import P2PSettings, default_store_path


PAIRING_PENDING = "pending"
PAIRING_ACCEPTED = "accepted"
PAIRING_REJECTED = "rejected"
PAIRING_EXPIRED = "expired"
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _pairings_file(store_path: Path | None = None) -> Path:
    root = Path(store_path).expanduser() if store_path is not None else default_store_path()
    if root.name == "pairings.json":
        return root
    return root / "pairings.json"


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return sorted({str(value).strip() for value in values if str(value).strip()})


@dataclass
class PairingSession:
    pairing_id: str
    code: str
    status: str
    expires_at: int
    created_at: int
    peer_id: str = ""
    peer_fingerprint: str = ""
    peer_label: str = ""
    capabilities: list[str] = field(default_factory=lambda: ["message"])
    allowed_company_ids: list[str] = field(default_factory=list)
    accepted_at: int = 0
    rejected_at: int = 0
    reason: str = ""
    # v2 claim fields
    claimed_device_id: str = ""
    claimed_device_label: str = ""
    claimed_device_public_key: str = ""
    claimed_capabilities: list[str] = field(default_factory=list)
    claimed_at: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PairingSession":
        return cls(
            pairing_id=str(value.get("pairing_id") or ""),
            code=str(value.get("code") or ""),
            status=str(value.get("status") or PAIRING_PENDING),
            expires_at=int(value.get("expires_at") or 0),
            created_at=int(value.get("created_at") or _now_ms()),
            peer_id=str(value.get("peer_id") or ""),
            peer_fingerprint=str(value.get("peer_fingerprint") or value.get("fingerprint") or ""),
            peer_label=str(value.get("peer_label") or value.get("label") or ""),
            capabilities=_string_list(value.get("capabilities")) or ["message"],
            allowed_company_ids=_string_list(value.get("allowed_company_ids")),
            accepted_at=int(value.get("accepted_at") or 0),
            rejected_at=int(value.get("rejected_at") or 0),
            reason=str(value.get("reason") or ""),
            claimed_device_id=str(value.get("claimed_device_id") or ""),
            claimed_device_label=str(value.get("claimed_device_label") or ""),
            claimed_device_public_key=str(value.get("claimed_device_public_key") or ""),
            claimed_capabilities=_string_list(value.get("claimed_capabilities")),
            claimed_at=int(value.get("claimed_at") or 0),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "pairing_id": self.pairing_id,
            "code": self.code,
            "status": self.status,
            "expires_at": int(self.expires_at),
            "created_at": int(self.created_at),
            "peer_id": self.peer_id,
            "peer_fingerprint": self.peer_fingerprint,
            "peer_label": self.peer_label,
            "capabilities": list(self.capabilities),
            "allowed_company_ids": list(self.allowed_company_ids),
            "accepted_at": int(self.accepted_at),
            "rejected_at": int(self.rejected_at),
            "reason": self.reason,
            "claimed_device_id": self.claimed_device_id,
            "claimed_device_label": self.claimed_device_label,
            "claimed_capabilities": list(self.claimed_capabilities),
            "claimed_at": int(self.claimed_at),
        }

    def expired(self, now: int | None = None) -> bool:
        return int(self.expires_at) <= int(now if now is not None else _now_ms())


class PairingManager:
    def __init__(self, store_path: Path | None = None, *, peer_store: PeerStore | None = None) -> None:
        self.store_path = Path(store_path).expanduser() if store_path is not None else default_store_path()
        self.path = _pairings_file(self.store_path)
        self.peer_store = peer_store or PeerStore(self.store_path)
        self._data = self._load()

    def start_pairing(
        self,
        *,
        peer_id: str = "",
        peer_fingerprint: str = "",
        peer_label: str = "",
        ttl_seconds: int | None = None,
        capabilities: list[str] | None = None,
        allowed_company_ids: list[str] | None = None,
        settings: P2PSettings | None = None,
    ) -> PairingSession:
        ttl = int(ttl_seconds or (settings.pairing_ttl_seconds if settings is not None else 300))
        now = _now_ms()
        session = PairingSession(
            pairing_id="pair-" + uuid.uuid4().hex,
            code=self._new_unique_code(),
            status=PAIRING_PENDING,
            expires_at=now + max(1, ttl) * 1000,
            created_at=now,
            peer_id=str(peer_id or "").strip(),
            peer_fingerprint=str(peer_fingerprint or "").strip(),
            peer_label=str(peer_label or "").strip(),
            capabilities=_string_list(capabilities) or ["message"],
            allowed_company_ids=_string_list(allowed_company_ids),
        )
        sessions = self._sessions()
        sessions[session.pairing_id] = session
        self._save_sessions(sessions)
        return session

    def accept_pairing(
        self,
        code: str,
        *,
        peer_id: str = "",
        peer_fingerprint: str = "",
        peer_label: str = "",
        hmac_secret: str = "",
        capabilities: list[str] | None = None,
        allowed_company_ids: list[str] | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        session = self._find_by_code(code)
        if session is None:
            return {"ok": False, "reason": "pairing code not found", "code": "PAIRING_NOT_FOUND"}
        now = int(now_ms if now_ms is not None else _now_ms())
        if session.status != PAIRING_PENDING:
            return {"ok": False, "reason": f"pairing is {session.status}", "code": "PAIRING_NOT_PENDING"}
        if session.expired(now):
            session.status = PAIRING_EXPIRED
            session.reason = "expired"
            self._replace(session)
            return {"ok": False, "reason": "pairing code expired", "code": "PAIRING_EXPIRED"}

        resolved_peer_id = str(peer_id or session.peer_id or "").strip()
        if not resolved_peer_id:
            return {"ok": False, "reason": "peer_id is required", "code": "INVALID_INPUT"}
        secret = str(hmac_secret or "").strip() or generate_shared_secret()
        resolved_capabilities = _string_list(capabilities) or session.capabilities or ["message"]
        resolved_allowed_companies = _string_list(allowed_company_ids) or session.allowed_company_ids
        peer = self.peer_store.approve_peer(
            resolved_peer_id,
            fingerprint=str(peer_fingerprint or session.peer_fingerprint or "").strip(),
            hmac_secret=secret,
            capabilities=resolved_capabilities,
            allowed_company_ids=resolved_allowed_companies,
            label=str(peer_label or session.peer_label or "").strip(),
            metadata={"pairing_id": session.pairing_id},
        )
        session.status = PAIRING_ACCEPTED
        session.accepted_at = now
        session.peer_id = peer.peer_id
        session.peer_fingerprint = peer.fingerprint
        session.peer_label = peer.label
        session.capabilities = list(peer.capabilities)
        session.allowed_company_ids = list(peer.allowed_company_ids)
        self._replace(session)
        return {
            "ok": True,
            "pairing": session.as_dict(),
            "peer": peer.as_dict(),
            "hmac_secret": secret,
        }

    def reject_pairing(self, code: str, *, reason: str = "", now_ms: int | None = None) -> dict[str, Any]:
        session = self._find_by_code(code)
        if session is None:
            return {"ok": False, "reason": "pairing code not found", "code": "PAIRING_NOT_FOUND"}
        if session.status != PAIRING_PENDING:
            return {"ok": False, "reason": f"pairing is {session.status}", "code": "PAIRING_NOT_PENDING"}
        session.status = PAIRING_REJECTED
        session.rejected_at = int(now_ms if now_ms is not None else _now_ms())
        session.reason = str(reason or "rejected")
        self._replace(session)
        return {"ok": True, "pairing": session.as_dict()}

    def claim_pairing(
        self,
        pairing_id: str,
        *,
        device_id: str,
        device_label: str = "",
        device_public_key: str = "",
        requested_capabilities: list[str] | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        """Record a mobile device's claim against a pending pairing session.

        The PC operator must still approve before a device token is issued.
        """
        sessions = self._sessions()
        session = sessions.get(str(pairing_id or "").strip())
        if session is None:
            return {"ok": False, "reason": "pairing not found", "code": "PAIRING_NOT_FOUND"}
        now = int(now_ms if now_ms is not None else _now_ms())
        if session.status != PAIRING_PENDING:
            return {"ok": False, "reason": f"pairing is {session.status}", "code": "PAIRING_NOT_PENDING"}
        if session.expired(now):
            session.status = PAIRING_EXPIRED
            session.reason = "expired"
            self._replace(session)
            return {"ok": False, "reason": "pairing code expired", "code": "PAIRING_EXPIRED"}
        session.claimed_device_id = str(device_id or "").strip()
        session.claimed_device_label = str(device_label or "").strip()
        session.claimed_device_public_key = str(device_public_key or "").strip()
        session.claimed_capabilities = _string_list(requested_capabilities) or session.capabilities
        session.claimed_at = now
        self._replace(session)
        return {"ok": True, "pairing": session.as_dict()}

    def get_pairing(self, pairing_id: str) -> PairingSession | None:
        return self._sessions().get(str(pairing_id or "").strip())

    def approve_pairing_v2(
        self,
        pairing_id: str,
        *,
        scopes: list[str] | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        """Approve a claimed pairing and mark it accepted (v2 flow).

        The actual device token is issued by the caller (DeviceStore) since
        PairingManager should not depend on crypto. This method just flips
        the session status and returns claim info for token issuance.
        """
        sessions = self._sessions()
        session = sessions.get(str(pairing_id or "").strip())
        if session is None:
            return {"ok": False, "reason": "pairing not found", "code": "PAIRING_NOT_FOUND"}
        now = int(now_ms if now_ms is not None else _now_ms())
        if session.status != PAIRING_PENDING:
            return {"ok": False, "reason": f"pairing is {session.status}", "code": "PAIRING_NOT_PENDING"}
        if not session.claimed_device_id:
            return {"ok": False, "reason": "pairing has not been claimed", "code": "NOT_CLAIMED"}
        if session.expired(now):
            session.status = PAIRING_EXPIRED
            session.reason = "expired"
            self._replace(session)
            return {"ok": False, "reason": "pairing code expired", "code": "PAIRING_EXPIRED"}
        resolved_scopes = _string_list(scopes) or session.claimed_capabilities or ["chat.read", "chat.write", "tools.observe"]
        session.status = PAIRING_ACCEPTED
        session.accepted_at = now
        session.peer_id = session.claimed_device_id
        session.peer_label = session.claimed_device_label
        session.capabilities = resolved_scopes
        self._replace(session)
        return {
            "ok": True,
            "pairing": session.as_dict(),
            "device_id": session.claimed_device_id,
            "device_label": session.claimed_device_label,
            "device_public_key": session.claimed_device_public_key,
            "scopes": resolved_scopes,
        }

    def list_pairings(self) -> list[dict[str, Any]]:
        self.cleanup_expired()
        return [session.as_dict() for session in self._sessions().values()]

    def cleanup_expired(self, *, now_ms: int | None = None) -> None:
        now = int(now_ms if now_ms is not None else _now_ms())
        sessions = self._sessions()
        changed = False
        for session in sessions.values():
            if session.status == PAIRING_PENDING and session.expired(now):
                session.status = PAIRING_EXPIRED
                session.reason = "expired"
                changed = True
        if changed:
            self._save_sessions(sessions)

    def _find_by_code(self, code: str) -> PairingSession | None:
        target = str(code or "").strip().upper()
        if not target:
            return None
        for session in self._sessions().values():
            if session.code.upper() == target:
                return session
        return None

    def _replace(self, session: PairingSession) -> None:
        sessions = self._sessions()
        sessions[session.pairing_id] = session
        self._save_sessions(sessions)

    def _new_unique_code(self) -> str:
        existing = {session.code for session in self._sessions().values()}
        while True:
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
            code = code[:4] + "-" + code[4:]
            if code not in existing:
                return code

    def _sessions(self) -> dict[str, PairingSession]:
        raw = self._data.setdefault("pairings", {})
        if not isinstance(raw, dict):
            raw = {}
            self._data["pairings"] = raw
        return {
            key: PairingSession.from_dict(value)
            for key, value in raw.items()
            if isinstance(value, dict) and str(value.get("pairing_id") or key).strip()
        }

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("schema_version", 1)
        data.setdefault("pairings", {})
        return data

    def _save_sessions(self, sessions: dict[str, PairingSession]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data["schema_version"] = 1
        self._data["updated_at"] = _now_ms()
        self._data["pairings"] = {session_id: session.as_dict() for session_id, session in sessions.items()}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
