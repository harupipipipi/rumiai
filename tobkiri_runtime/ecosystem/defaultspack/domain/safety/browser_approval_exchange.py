"""Ephemeral, audience-bound browser approval exchanges.

Exchange codes are not approval credentials.  They may only be redeemed once,
over the authenticated local HTTP channel, for a signed UI-operator context.
Only a digest of each code is retained and the store is intentionally
process-local so the feature remains local-first.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any


DEFAULT_EXCHANGE_TTL_SECONDS = 60
MAX_EXCHANGE_TTL_SECONDS = 180


@dataclass(frozen=True)
class BrowserApprovalAudience:
    """The complete audience to which an exchange is bound."""

    request_id: str
    principal_id: str
    device_id: str
    origin: str
    window_id: str
    nonce: str


@dataclass
class _ExchangeRecord:
    exchange_id: str
    server_nonce: str
    audience: BrowserApprovalAudience
    issued_at: int
    expires_at: int
    state: str = "issued"


class BrowserApprovalExchangeStore:
    """Issue and atomically settle short-lived browser exchanges."""

    def __init__(self) -> None:
        self._records: dict[str, _ExchangeRecord] = {}
        self._exchange_ids: dict[str, str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def code_digest(code: str) -> str:
        """Return the non-reversible lookup digest for an opaque code."""
        return hashlib.sha256(str(code or "").encode("utf-8")).hexdigest()

    def issue(
        self,
        audience: BrowserApprovalAudience,
        *,
        now: int | None = None,
        ttl_seconds: int = DEFAULT_EXCHANGE_TTL_SECONDS,
    ) -> dict[str, Any]:
        """Issue a memory-only exchange code for an authenticated audience."""
        current = int(time.time() if now is None else now)
        ttl = max(15, min(int(ttl_seconds), MAX_EXCHANGE_TTL_SECONDS))
        code = secrets.token_urlsafe(32)
        exchange_id = secrets.token_urlsafe(12)
        server_nonce = secrets.token_urlsafe(24)
        digest = self.code_digest(code)
        with self._lock:
            self._purge_locked(current)
            self._records[digest] = _ExchangeRecord(
                exchange_id=exchange_id,
                server_nonce=server_nonce,
                audience=audience,
                issued_at=current,
                expires_at=current + ttl,
            )
            self._exchange_ids[exchange_id] = digest
        return {
            "exchange_id": exchange_id,
            "exchange_code": code,
            "server_nonce": server_nonce,
            "expires_at": current + ttl,
        }

    def redeem(
        self,
        code: str,
        audience: BrowserApprovalAudience,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Atomically consume an exchange when every audience field matches."""
        return self._settle(code, audience, next_state="consumed", now=now)

    def revoke(
        self,
        code: str,
        audience: BrowserApprovalAudience,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Atomically revoke an unconsumed exchange for its bound audience."""
        return self._settle(code, audience, next_state="revoked", now=now)

    def revoke_by_id(
        self,
        exchange_id: str,
        audience: BrowserApprovalAudience,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Revoke by non-secret identifier and the authenticated audience."""
        current = int(time.time() if now is None else now)
        with self._lock:
            digest = self._exchange_ids.get(str(exchange_id or ""))
            record = self._records.get(digest or "")
            if record is None:
                return {"success": False, "reason": "invalid"}
            if record.expires_at <= current:
                record.state = "expired"
                return {"success": False, "reason": "expired"}
            if record.audience != audience:
                return {"success": False, "reason": "audience_mismatch"}
            if record.state != "issued":
                return {"success": False, "reason": record.state}
            record.state = "revoked"
            return {
                "success": True,
                "request_id": record.audience.request_id,
                "expires_at": record.expires_at,
                "state": "revoked",
            }

    def _settle(
        self,
        code: str,
        audience: BrowserApprovalAudience,
        *,
        next_state: str,
        now: int | None,
    ) -> dict[str, Any]:
        current = int(time.time() if now is None else now)
        digest = self.code_digest(code)
        with self._lock:
            record = self._records.get(digest)
            if record is None:
                return {"success": False, "reason": "invalid"}
            if record.expires_at <= current:
                record.state = "expired"
                return {"success": False, "reason": "expired"}
            if record.audience != audience:
                return {"success": False, "reason": "audience_mismatch"}
            if record.state != "issued":
                return {"success": False, "reason": record.state}
            record.state = next_state
            return {
                "success": True,
                "request_id": record.audience.request_id,
                "expires_at": record.expires_at,
                "state": next_state,
                "server_nonce": record.server_nonce,
            }

    def _purge_locked(self, now: int) -> None:
        stale = [
            digest
            for digest, record in self._records.items()
            if record.expires_at + MAX_EXCHANGE_TTL_SECONDS <= now
        ]
        for digest in stale:
            record = self._records.pop(digest, None)
            if record is not None:
                self._exchange_ids.pop(record.exchange_id, None)


_STORE = BrowserApprovalExchangeStore()


def get_browser_approval_exchange_store() -> BrowserApprovalExchangeStore:
    """Return the process-local browser approval exchange store."""
    return _STORE
