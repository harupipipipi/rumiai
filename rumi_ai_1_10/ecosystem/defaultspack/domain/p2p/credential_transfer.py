"""Device-bound, one-time provider credential transfer state machine."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import uuid
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .json_store import file_lock, load_json_object, save_json_object
from .settings import default_store_path


TRANSFER_ALGORITHM = "X25519-HKDF-SHA256-AES-256-GCM"
TRANSFER_VERSION = 1
TRANSFER_TTL_SECONDS = 90
TERMINAL_STATES = {"accepted", "completed", "rejected", "expired", "revoked", "cancelled"}
_HKDF_SALT = b"rumi-provider-credential-transfer-v1"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _transfers_file(store_path: Path | None = None) -> Path:
    root = Path(store_path).expanduser() if store_path is not None else default_store_path()
    return root if root.name == "credential_transfers.json" else root / "credential_transfers.json"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(value: str) -> bytes:
    text = str(value or "").strip()
    return base64.urlsafe_b64decode(text + "=" * ((4 - len(text) % 4) % 4))


def _decode_public_key(value: str, prefix: str, expected_length: int) -> bytes:
    text = str(value or "").strip()
    if text.startswith(prefix):
        text = text[len(prefix) :]
    raw = _unb64url(text)
    if len(raw) != expected_length:
        raise ValueError(f"invalid {prefix[:-1]} public key")
    return raw


def _safe_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in {"envelope", "recipient_public_key", "recipient_signing_key", "redemption_challenge", "expiry_audited"}
    }


def redemption_message(record: dict[str, Any]) -> bytes:
    payload = {
        "transfer_id": str(record.get("transfer_id") or ""),
        "device_id": str(record.get("device_id") or ""),
        "provider_id": str(record.get("provider_id") or ""),
        "api_id": str(record.get("api_id") or ""),
        "expires_at": int(record.get("expires_at") or 0),
        "challenge": str(record.get("redemption_challenge") or ""),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def encrypt_credential_payload(
    payload: dict[str, Any],
    recipient_public_key: str,
    *,
    transfer_id: str,
    device_id: str,
    expires_at: int,
) -> dict[str, Any]:
    recipient = x25519.X25519PublicKey.from_public_bytes(
        _decode_public_key(recipient_public_key, "x25519:", 32)
    )
    ephemeral_private = x25519.X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    shared_secret = ephemeral_private.exchange(recipient)
    info = f"{transfer_id}:{device_id}:{expires_at}".encode("utf-8")
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=_HKDF_SALT, info=info).derive(shared_secret)
    aad = f"rumi-provider-credential-transfer:v1:{transfer_id}:{device_id}:{expires_at}".encode("utf-8")
    nonce = secrets.token_bytes(12)
    cleartext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encrypted = AESGCM(key).encrypt(nonce, cleartext, aad)
    return {
        "version": TRANSFER_VERSION,
        "alg": TRANSFER_ALGORITHM,
        "ephemeral_public_key": "x25519:" + _b64url(ephemeral_public),
        "nonce": _b64url(nonce),
        "ciphertext": _b64url(encrypted[:-16]),
        "tag": _b64url(encrypted[-16:]),
        "aad": _b64url(aad),
    }


class CredentialTransferStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self.path = _transfers_file(store_path)

    def create(
        self,
        *,
        device_id: str,
        device_label: str,
        profile_id: str,
        provider_id: str,
        api_id: str,
        provider_label: str,
        recipient_public_key: str,
        recipient_signing_key: str,
        ttl_seconds: int = TRANSFER_TTL_SECONDS,
    ) -> dict[str, Any]:
        _decode_public_key(recipient_public_key, "x25519:", 32)
        _decode_public_key(recipient_signing_key, "ed25519:", 32)
        now = _now_ms()
        record = {
            "transfer_id": "ctr_" + uuid.uuid4().hex,
            "status": "awaiting_confirmation",
            "device_id": device_id,
            "device_label": device_label,
            "profile_id": profile_id,
            "provider_id": provider_id,
            "api_id": api_id,
            "provider_label": provider_label or provider_id,
            "recipient_public_key": recipient_public_key,
            "recipient_signing_key": recipient_signing_key,
            "redemption_challenge": "rch_" + secrets.token_urlsafe(24),
            "created_at": now,
            "expires_at": now + max(1, min(int(ttl_seconds), TRANSFER_TTL_SECONDS)) * 1000,
            "confirmed_at": 0,
            "accepted_at": 0,
            "completed_at": 0,
            "reason": "",
            "expiry_audited": False,
            "envelope": {},
        }
        with self._lock():
            data = self._load()
            data["transfers"][record["transfer_id"]] = record
            self._save(data)
        return _safe_record(record)

    def confirm(self, transfer_id: str, *, payload: dict[str, Any], expected: dict[str, str]) -> dict[str, Any]:
        with self._lock():
            data = self._load()
            record = self._record(data, transfer_id)
            self._expire(record)
            if record["status"] != "awaiting_confirmation":
                raise ValueError(f"transfer is {record['status']}")
            for key in ("device_id", "provider_id", "api_id"):
                if str(expected.get(key) or "") != str(record.get(key) or ""):
                    raise PermissionError("transfer confirmation changed")
            record["envelope"] = encrypt_credential_payload(
                payload,
                str(record["recipient_public_key"]),
                transfer_id=str(record["transfer_id"]),
                device_id=str(record["device_id"]),
                expires_at=int(record["expires_at"]),
            )
            record["status"] = "pending"
            record["confirmed_at"] = _now_ms()
            self._save(data)
            return _safe_record(record)

    def list_for_device(self, device_id: str) -> list[dict[str, Any]]:
        with self._lock():
            data = self._load()
            changed = False
            result = []
            for record in data["transfers"].values():
                before = str(record.get("status") or "")
                self._expire(record)
                changed = changed or before != record.get("status")
                if record.get("device_id") == device_id and record.get("status") in {"pending", "accepted"}:
                    safe = _safe_record(record)
                    safe["redemption_challenge"] = record.get("redemption_challenge")
                    result.append(safe)
            if changed:
                self._save(data)
            return sorted(result, key=lambda item: int(item.get("created_at") or 0), reverse=True)

    def get_admin(self, transfer_id: str) -> dict[str, Any]:
        with self._lock():
            data = self._load()
            record = self._record(data, transfer_id)
            before = record["status"]
            self._expire(record)
            if before != record["status"]:
                self._save(data)
            return _safe_record(record)

    def claim_expiry_audits(
        self,
        *,
        device_id: str = "",
        transfer_id: str = "",
    ) -> list[dict[str, Any]]:
        """Atomically claim newly expired records for exactly-once auditing."""
        with self._lock():
            data = self._load()
            claimed: list[dict[str, Any]] = []
            for record in data["transfers"].values():
                if transfer_id and record.get("transfer_id") != transfer_id:
                    continue
                if device_id and record.get("device_id") != device_id:
                    continue
                if record.get("status") != "expired" or record.get("expiry_audited") is True:
                    continue
                record["expiry_audited"] = True
                claimed.append(_safe_record(record))
            if claimed:
                self._save(data)
            return claimed

    def redeem(self, transfer_id: str, *, device_id: str, signature: str) -> dict[str, Any]:
        with self._lock():
            data = self._load()
            record = self._record(data, transfer_id)
            self._expire(record)
            if record.get("device_id") != device_id:
                raise PermissionError("transfer is not for this device")
            if record["status"] != "pending":
                raise ValueError(f"transfer is {record['status']}")
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(
                _decode_public_key(str(record["recipient_signing_key"]), "ed25519:", 32)
            )
            try:
                public_key.verify(_unb64url(signature), hashlib.sha256(redemption_message(record)).digest())
            except (InvalidSignature, ValueError) as exc:
                raise PermissionError("recipient proof rejected") from exc
            envelope = dict(record.get("envelope") or {})
            if not envelope:
                raise ValueError("encrypted envelope unavailable")
            record["status"] = "accepted"
            record["accepted_at"] = _now_ms()
            record["envelope"] = {}
            self._save(data)
            return {"transfer": _safe_record(record), "envelope": envelope}

    def transition(self, transfer_id: str, *, status: str, actor_device_id: str = "", reason: str = "") -> dict[str, Any]:
        if status not in {"rejected", "revoked", "cancelled", "completed"}:
            raise ValueError("invalid transfer transition")
        with self._lock():
            data = self._load()
            record = self._record(data, transfer_id)
            self._expire(record)
            if actor_device_id and record.get("device_id") != actor_device_id:
                raise PermissionError("transfer is not for this device")
            allowed = {
                "rejected": {"pending"},
                "cancelled": {"awaiting_confirmation", "pending"},
                # Once redeem returns the envelope, delivery has happened.  The
                # PC can no longer truthfully revoke that delivered material.
                "revoked": {"awaiting_confirmation", "pending"},
                "completed": {"accepted"},
            }
            if record["status"] not in allowed[status]:
                raise ValueError(f"transfer is {record['status']}")
            record["status"] = status
            record["reason"] = str(reason or status)[:160]
            record["envelope"] = {}
            record[f"{status}_at"] = _now_ms()
            self._save(data)
            return _safe_record(record)

    def revoke_for_device(self, device_id: str) -> int:
        with self._lock():
            data = self._load()
            count = 0
            for record in data["transfers"].values():
                if record.get("device_id") == device_id and record.get("status") not in TERMINAL_STATES:
                    record["status"] = "revoked"
                    record["reason"] = "paired device revoked"
                    record["revoked_at"] = _now_ms()
                    record["envelope"] = {}
                    count += 1
            if count:
                self._save(data)
            return count

    def _expire(self, record: dict[str, Any]) -> None:
        if record.get("status") not in TERMINAL_STATES and _now_ms() >= int(record.get("expires_at") or 0):
            record["status"] = "expired"
            record["reason"] = "expired"
            record["expired_at"] = _now_ms()
            record["envelope"] = {}

    def _record(self, data: dict[str, Any], transfer_id: str) -> dict[str, Any]:
        record = data["transfers"].get(str(transfer_id or "").strip())
        if not isinstance(record, dict):
            raise KeyError("transfer not found")
        return record

    def _load(self) -> dict[str, Any]:
        data = load_json_object(self.path)
        data.setdefault("schema_version", 1)
        data.setdefault("transfers", {})
        if not isinstance(data["transfers"], dict):
            data["transfers"] = {}
        return data

    def _save(self, data: dict[str, Any]) -> None:
        data["updated_at"] = _now_ms()
        save_json_object(self.path, data)

    def _lock(self) -> AbstractContextManager[None]:
        return file_lock(self.path, lock_name="credential transfer store")
