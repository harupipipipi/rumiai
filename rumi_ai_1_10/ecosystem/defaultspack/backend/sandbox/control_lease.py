from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from .errors import (
    DESKTOP_CONTROL_CONFLICT,
    DESKTOP_LEASE_EXPIRED,
    DESKTOP_LEASE_INVALID,
    DESKTOP_LEASE_REQUIRED,
    SandboxContractError,
)
from .policy import require_canonical_id


@dataclass(frozen=True)
class ControlLeaseGrant:
    seat_id: str
    owner_id: str
    lease_id: str
    token: str
    acquired_at: float
    expires_at: float

    def to_response(self) -> dict[str, object]:
        return {
            "seat_id": self.seat_id,
            "owner_id": self.owner_id,
            "lease_id": self.lease_id,
            "lease_token": self.token,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class ControlLeaseState:
    seat_id: str
    owner_id: str
    lease_id: str
    acquired_at: float
    expires_at: float

    def to_dict(self) -> dict[str, object]:
        return {
            "seat_id": self.seat_id,
            "owner_id": self.owner_id,
            "lease_id": self.lease_id,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
        }


@dataclass
class _LeaseRecord:
    seat_id: str
    owner_id: str
    lease_id: str
    token_hash: str
    acquired_at: float
    expires_at: float

    def state(self) -> ControlLeaseState:
        return ControlLeaseState(
            seat_id=self.seat_id,
            owner_id=self.owner_id,
            lease_id=self.lease_id,
            acquired_at=self.acquired_at,
            expires_at=self.expires_at,
        )


class ControlLeaseManager:
    def __init__(
        self,
        *,
        ttl_seconds: float = 30.0,
        time_fn: Callable[[], float] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self._time_fn = time_fn or time.time
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._leases: dict[str, _LeaseRecord] = {}

    def acquire(self, seat_id: str, owner_id: str) -> ControlLeaseGrant:
        seat_id = require_canonical_id(seat_id, field="seat_id")
        owner_id = require_canonical_id(owner_id, field="owner_id")
        now = self._time_fn()
        active = self._active_record(seat_id, now=now)
        if active is not None:
            raise SandboxContractError(
                DESKTOP_CONTROL_CONFLICT,
                "Desktop control is already leased",
                status_code=409,
                details={"seat_id": seat_id, "owner_id": active.owner_id, "expires_at": active.expires_at},
            )

        token = self._token_factory()
        if not isinstance(token, str) or not token:
            raise RuntimeError("lease token factory must return a non-empty string")
        lease_id = str(uuid.uuid4())
        expires_at = now + self.ttl_seconds
        self._leases[seat_id] = _LeaseRecord(
            seat_id=seat_id,
            owner_id=owner_id,
            lease_id=lease_id,
            token_hash=self._hash_token(seat_id, lease_id, token),
            acquired_at=now,
            expires_at=expires_at,
        )
        return ControlLeaseGrant(
            seat_id=seat_id,
            owner_id=owner_id,
            lease_id=lease_id,
            token=token,
            acquired_at=now,
            expires_at=expires_at,
        )

    def renew(self, seat_id: str, owner_id: str, lease_token: str) -> ControlLeaseState:
        seat_id = require_canonical_id(seat_id, field="seat_id")
        owner_id = require_canonical_id(owner_id, field="owner_id")
        record = self._require_valid_record(seat_id, lease_token)
        if record.owner_id != owner_id:
            raise SandboxContractError(DESKTOP_LEASE_INVALID, "Lease owner does not match", status_code=403)
        record.expires_at = self._time_fn() + self.ttl_seconds
        return record.state()

    def release(self, seat_id: str, owner_id: str, lease_token: str) -> bool:
        seat_id = require_canonical_id(seat_id, field="seat_id")
        owner_id = require_canonical_id(owner_id, field="owner_id")
        record = self._active_record(seat_id)
        if record is None:
            return False
        if record.owner_id != owner_id or not self._token_matches(record, lease_token):
            raise SandboxContractError(DESKTOP_LEASE_INVALID, "Lease token is invalid", status_code=403)
        self._leases.pop(seat_id, None)
        return True

    def invalidate(self, seat_id: str) -> None:
        self._leases.pop(require_canonical_id(seat_id, field="seat_id"), None)

    def active_lease(self, seat_id: str) -> ControlLeaseState | None:
        record = self._active_record(require_canonical_id(seat_id, field="seat_id"))
        return None if record is None else record.state()

    def validate_human_input(self, seat_id: str, lease_token: str | None) -> ControlLeaseState:
        seat_id = require_canonical_id(seat_id, field="seat_id")
        if not lease_token:
            raise SandboxContractError(DESKTOP_LEASE_REQUIRED, "A valid desktop control lease is required", status_code=409)
        return self._require_valid_record(seat_id, lease_token).state()

    def validate_ai_input(self, seat_id: str) -> None:
        seat_id = require_canonical_id(seat_id, field="seat_id")
        record = self._active_record(seat_id)
        if record is not None:
            raise SandboxContractError(
                DESKTOP_CONTROL_CONFLICT,
                "AI desktop input is blocked while a human control lease is active",
                status_code=409,
                details={"seat_id": seat_id, "owner_id": record.owner_id, "expires_at": record.expires_at},
            )

    def debug_snapshot(self) -> dict[str, dict[str, object]]:
        snapshot: dict[str, dict[str, object]] = {}
        for seat_id, record in self._leases.items():
            snapshot[seat_id] = {
                "seat_id": record.seat_id,
                "owner_id": record.owner_id,
                "lease_id": record.lease_id,
                "token_hash": record.token_hash,
                "acquired_at": record.acquired_at,
                "expires_at": record.expires_at,
            }
        return snapshot

    def _active_record(self, seat_id: str, *, now: float | None = None) -> _LeaseRecord | None:
        now = self._time_fn() if now is None else now
        record = self._leases.get(seat_id)
        if record is None:
            return None
        if record.expires_at <= now:
            self._leases.pop(seat_id, None)
            return None
        return record

    def _require_valid_record(self, seat_id: str, lease_token: str) -> _LeaseRecord:
        record = self._leases.get(seat_id)
        if record is None:
            raise SandboxContractError(DESKTOP_LEASE_REQUIRED, "A valid desktop control lease is required", status_code=409)
        if record.expires_at <= self._time_fn():
            self._leases.pop(seat_id, None)
            raise SandboxContractError(DESKTOP_LEASE_EXPIRED, "Desktop control lease has expired", status_code=409)
        if not self._token_matches(record, lease_token):
            raise SandboxContractError(DESKTOP_LEASE_REQUIRED, "A valid desktop control lease is required", status_code=409)
        return record

    def _token_matches(self, record: _LeaseRecord, lease_token: str) -> bool:
        if not isinstance(lease_token, str) or not lease_token:
            return False
        expected = self._hash_token(record.seat_id, record.lease_id, lease_token)
        return hmac.compare_digest(record.token_hash, expected)

    @staticmethod
    def _hash_token(seat_id: str, lease_id: str, lease_token: str) -> str:
        payload = f"{seat_id}:{lease_id}:{lease_token}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
