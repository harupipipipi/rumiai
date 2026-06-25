"""Profile-scoped device public key registry for mobile approvals."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..compat import safe_chmod
from ..hmac_key_manager import generate_or_load_signing_key
from ..paths import USER_DATA_DIR


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_key(profile_id: str, device_id: str) -> str:
    return hashlib.sha256(f"{profile_id}\0{device_id}".encode("utf-8")).hexdigest()


def _b64decode(value: str) -> bytes:
    text = value.strip()
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _public_key_bytes(public_key: str | bytes) -> bytes:
    if isinstance(public_key, bytes):
        raw = public_key
    else:
        text = str(public_key or "").strip()
        if text.startswith("ed25519:"):
            text = text.split(":", 1)[1]
        if "BEGIN PUBLIC KEY" in text:
            loaded = serialization.load_pem_public_key(text.encode("utf-8"))
            if not isinstance(loaded, Ed25519PublicKey):
                raise ValueError("device public key must be Ed25519")
            return loaded.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        raw = _b64decode(text)
    if len(raw) != 32:
        raise ValueError("device public key must be 32 raw Ed25519 bytes")
    Ed25519PublicKey.from_public_bytes(raw)
    return raw


@dataclass(frozen=True)
class DeviceKeyRecord:
    profile_id: str
    device_id: str
    key_id: str
    public_key: str
    key_type: str = "ed25519"
    created_at: str = ""
    revoked_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "device_id": self.device_id,
            "key_id": self.key_id,
            "public_key": self.public_key,
            "key_type": self.key_type,
            "created_at": self.created_at,
            "revoked_at": self.revoked_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceKeyRecord":
        return cls(
            profile_id=str(data.get("profile_id") or ""),
            device_id=str(data.get("device_id") or ""),
            key_id=str(data.get("key_id") or ""),
            public_key=str(data.get("public_key") or ""),
            key_type=str(data.get("key_type") or "ed25519"),
            created_at=str(data.get("created_at") or ""),
            revoked_at=str(data.get("revoked_at") or "") or None,
        )


class DeviceKeyRegistry:
    """Signed public-key registry keyed by profile and device."""

    def __init__(
        self,
        base_dir: str | Path | None = None,
        *,
        secret_key: str | bytes | None = None,
    ) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else USER_DATA_DIR / "authority" / "device_keys"
        if isinstance(secret_key, bytes):
            self._secret_key = secret_key
        elif secret_key:
            self._secret_key = str(secret_key).encode("utf-8")
        else:
            self._secret_key = generate_or_load_signing_key(
                USER_DATA_DIR / "permissions" / ".authority_device_key"
            )
        self._lock = threading.RLock()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def register_device_key(
        self,
        *,
        profile_id: str,
        device_id: str,
        public_key: str | bytes,
    ) -> DeviceKeyRecord:
        profile_id = _required(profile_id, "profile_id")
        device_id = _required(device_id, "device_id")
        raw_key = _public_key_bytes(public_key)
        key_id = hashlib.sha256(raw_key).hexdigest()[:24]
        record = DeviceKeyRecord(
            profile_id=profile_id,
            device_id=device_id,
            key_id=key_id,
            public_key=_b64encode(raw_key),
            created_at=_now_ts(),
        )
        with self._lock:
            self._write_record(record)
        return record

    def get_device_key(self, *, profile_id: str, device_id: str) -> DeviceKeyRecord | None:
        with self._lock:
            data = self._read_payload(self._path(profile_id, device_id))
        if not data:
            return None
        record = DeviceKeyRecord.from_dict(data)
        if record.revoked_at:
            return None
        return record

    def revoke_device_key(self, *, profile_id: str, device_id: str) -> bool:
        with self._lock:
            path = self._path(profile_id, device_id)
            data = self._read_payload(path)
            if not data:
                return False
            data["revoked_at"] = _now_ts()
            self._write_payload(path, data)
            return True

    def verify_signature(
        self,
        *,
        profile_id: str,
        device_id: str,
        payload_hash: str,
        signature: str,
    ) -> bool:
        record = self.get_device_key(profile_id=profile_id, device_id=device_id)
        if record is None or record.key_type != "ed25519":
            return False
        try:
            public_key = Ed25519PublicKey.from_public_bytes(_b64decode(record.public_key))
            signature_bytes = _b64decode(signature)
            message = bytes.fromhex(str(payload_hash or ""))
            public_key.verify(signature_bytes, message)
            return True
        except (InvalidSignature, TypeError, ValueError, binascii.Error):
            return False

    def _path(self, profile_id: str, device_id: str) -> Path:
        return self._base_dir / f"{_safe_key(str(profile_id or ''), str(device_id or ''))}.json"

    def _signature(self, payload: dict[str, Any]) -> str:
        filtered = {key: value for key, value in payload.items() if key != "_hmac_signature"}
        return hmac.new(self._secret_key, _canonical_json(filtered).encode("utf-8"), hashlib.sha256).hexdigest()

    def _write_record(self, record: DeviceKeyRecord) -> None:
        self._write_payload(self._path(record.profile_id, record.device_id), record.to_dict())

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


def _required(value: str | None, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned
