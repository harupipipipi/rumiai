"""One-time desktop access exchange and scoped session credentials."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


DEFAULT_CODE_TTL_SECONDS = 60
DEFAULT_CREDENTIAL_TTL_SECONDS = 300
MAX_CODE_TTL_SECONDS = 300
MAX_CREDENTIAL_TTL_SECONDS = 3600


class DesktopAccessExchange:
    """Persist hashes and public metadata for desktop access grants."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self._clock = clock
        self._lock = threading.RLock()
        self._codes: dict[str, dict[str, Any]] = {}
        self._credentials: dict[str, dict[str, Any]] = {}
        self._load()

    def issue(
        self,
        *,
        audience: str,
        origin: str,
        principal_id: str,
        device_id: str,
        session_id: str,
        seat_id: str,
        operations: Iterable[str],
        code_ttl_seconds: int = DEFAULT_CODE_TTL_SECONDS,
        credential_ttl_seconds: int = DEFAULT_CREDENTIAL_TTL_SECONDS,
    ) -> dict[str, Any]:
        """Issue a one-time code bound to server-authenticated context."""
        now = self._clock()
        code = f"rumi_dxc_{secrets.token_urlsafe(32)}"
        code_id = f"dxc-{secrets.token_urlsafe(12)}"
        operation_set = sorted({str(item).strip() for item in operations if str(item).strip()})
        if not operation_set:
            raise ValueError("At least one desktop operation is required.")
        code_ttl = max(1, min(int(code_ttl_seconds), MAX_CODE_TTL_SECONDS))
        credential_ttl = max(1, min(int(credential_ttl_seconds), MAX_CREDENTIAL_TTL_SECONDS))
        record = {
            "code_id": code_id,
            "code_hash": _secret_hash(code),
            "audience": _required(audience, "audience"),
            "origin": _required(origin, "origin"),
            "principal_id": _required(principal_id, "principal_id"),
            "device_id": _required(device_id, "device_id"),
            "session_id": _required(session_id, "session_id"),
            "seat_id": _required(seat_id, "seat_id"),
            "operations": operation_set,
            "issued_at": now,
            "expires_at": now + code_ttl,
            "credential_ttl_seconds": credential_ttl,
            "status": "active",
        }
        with self._lock:
            self._codes[code_id] = record
            self._save()
        return {"exchange_code": code, **_public(record)}

    def exchange(self, code: str, *, context: Mapping[str, str]) -> dict[str, Any]:
        """Atomically consume a code and rotate credentials for its session."""
        digest = _secret_hash(_required(code, "exchange_code"))
        with self._lock:
            now = self._clock()
            record = next(
                (item for item in self._codes.values() if secrets.compare_digest(item["code_hash"], digest)),
                None,
            )
            if record is None:
                return _error("DESKTOP_EXCHANGE_CODE_INVALID", "Desktop exchange code is invalid.", 403)
            if record["status"] != "active":
                return _error("DESKTOP_EXCHANGE_CODE_REPLAYED", "Desktop exchange code was already used or revoked.", 409)
            if now >= float(record["expires_at"]):
                record["status"] = "expired"
                self._save()
                return _error("DESKTOP_EXCHANGE_CODE_EXPIRED", "Desktop exchange code expired.", 410)
            mismatch = _binding_mismatch(record, context)
            if mismatch:
                return _error("DESKTOP_EXCHANGE_BINDING_MISMATCH", f"Desktop exchange {mismatch} does not match.", 403)
            record["status"] = "consumed"
            record["consumed_at"] = now
            self._revoke_matching(record, reason="rotated", now=now)
            credential = f"rumi_dsc_{secrets.token_urlsafe(32)}"
            credential_record = {
                **{key: record[key] for key in _BINDING_KEYS},
                "credential_id": f"dsc-{secrets.token_urlsafe(12)}",
                "credential_hash": _secret_hash(credential),
                "operations": list(record["operations"]),
                "issued_at": now,
                "expires_at": now + int(record["credential_ttl_seconds"]),
                "status": "active",
                "code_id": record["code_id"],
            }
            self._credentials[credential_record["credential_id"]] = credential_record
            self._save()
            return {"ok": True, "session_credential": credential, **_public(credential_record)}

    def authorize(
        self,
        credential: str,
        *,
        seat_id: str,
        operation: str,
        context: Mapping[str, str],
    ) -> dict[str, Any]:
        """Authorize one explicit operation using trusted request context."""
        digest = _secret_hash(str(credential or ""))
        with self._lock:
            now = self._clock()
            record = next(
                (item for item in self._credentials.values() if secrets.compare_digest(item["credential_hash"], digest)),
                None,
            )
            if record is None:
                return _error("DESKTOP_SESSION_CREDENTIAL_INVALID", "Desktop session credential is invalid.", 403)
            if record["status"] != "active":
                return _error("DESKTOP_SESSION_CREDENTIAL_REVOKED", "Desktop session credential is revoked.", 403)
            if now >= float(record["expires_at"]):
                record["status"] = "expired"
                self._save()
                return _error("DESKTOP_SESSION_CREDENTIAL_EXPIRED", "Desktop session credential expired.", 403)
            if not secrets.compare_digest(str(record["seat_id"]), str(seat_id)):
                return _error("DESKTOP_SESSION_SEAT_MISMATCH", "Desktop session credential has the wrong seat.", 403)
            mismatch = _binding_mismatch(record, context)
            if mismatch:
                return _error("DESKTOP_SESSION_BINDING_MISMATCH", f"Desktop session {mismatch} does not match.", 403)
            if operation not in record["operations"]:
                return _error("DESKTOP_OPERATION_NOT_AUTHORIZED", "Desktop operation is outside the credential scope.", 403)
            return {"ok": True, "credential_id": record["credential_id"]}

    def list_metadata(self, *, seat_id: str | None = None) -> list[dict[str, Any]]:
        """Return grant metadata without hashes or bearer secrets."""
        with self._lock:
            self.expire()
            records = [*_map_public(self._codes.values()), *_map_public(self._credentials.values())]
            return [item for item in records if not seat_id or item.get("seat_id") == seat_id]

    def revoke(
        self,
        identifier: str,
        *,
        seat_id: str | None = None,
        reason: str = "revoked",
    ) -> bool:
        """Revoke a code or credential by its public identifier."""
        with self._lock:
            record = self._codes.get(identifier) or self._credentials.get(identifier)
            if not record or (seat_id is not None and record.get("seat_id") != seat_id):
                return False
            record.update(status="revoked", revoked_at=self._clock(), revocation_reason=reason)
            self._save()
            return True

    def revoke_seat(self, seat_id: str, *, reason: str) -> int:
        """Revoke all grants for a seat after policy/lifecycle changes."""
        with self._lock:
            now = self._clock()
            changed = 0
            for record in [*self._codes.values(), *self._credentials.values()]:
                if record.get("seat_id") == seat_id and record.get("status") == "active":
                    record.update(status="revoked", revoked_at=now, revocation_reason=reason)
                    changed += 1
            if changed:
                self._save()
            return changed

    def expire(self) -> int:
        """Mark elapsed active grants expired."""
        with self._lock:
            now = self._clock()
            changed = 0
            for record in [*self._codes.values(), *self._credentials.values()]:
                if record.get("status") == "active" and now >= float(record["expires_at"]):
                    record["status"] = "expired"
                    changed += 1
            if changed:
                self._save()
            return changed

    def _revoke_matching(self, code: Mapping[str, Any], *, reason: str, now: float) -> None:
        for record in self._credentials.values():
            if all(record.get(key) == code.get(key) for key in ("principal_id", "device_id", "session_id", "seat_id")):
                if record.get("status") == "active":
                    record.update(status="revoked", revoked_at=now, revocation_reason=reason)

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        self._codes = _records(data.get("codes"), "code_id")
        self._credentials = _records(data.get("credentials"), "credential_id")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps({"version": 1, "codes": list(self._codes.values()), "credentials": list(self._credentials.values())}, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)


_BINDING_KEYS = ("audience", "origin", "principal_id", "device_id", "session_id", "seat_id")


def _secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required.")
    return text[:512]


def _binding_mismatch(record: Mapping[str, Any], context: Mapping[str, str]) -> str | None:
    for key in ("audience", "origin", "principal_id", "device_id", "session_id"):
        if not secrets.compare_digest(str(record.get(key) or ""), str(context.get(key) or "")):
            return key
    return None


def _public(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in {"code_hash", "credential_hash", "credential_ttl_seconds"}
    }


def _map_public(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_public(record) for record in records]


def _records(value: Any, id_key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    return {str(item[id_key]): dict(item) for item in value if isinstance(item, dict) and item.get(id_key)}


def _error(code: str, message: str, status_code: int) -> dict[str, Any]:
    return {"ok": False, "code": code, "error": message, "status_code": status_code}
