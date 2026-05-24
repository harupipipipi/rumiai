"""Trust-root and Ed25519 signature helpers for update artifacts."""

from __future__ import annotations

import base64
import binascii
import copy
import json
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..paths import PACK_STATE_DIR

TRUST_SCHEMA = "rumi.trust_roots.v1"
ED25519_SCHEME = "ed25519"
OFFICIAL_TRUST_ROOTS_PATH = Path(__file__).with_name("official_trust_roots.json")


class TrustError(RuntimeError):
    """Raised when an update artifact signature cannot be trusted."""


def default_trust_roots_path() -> Path:
    return PACK_STATE_DIR / "trust_roots.json"


def load_trust_roots(path: Path | None = None, *, bundled_path: Path | None = None) -> dict[str, Any]:
    """Load official bundled keys plus user-added public keys.

    Official keys are merged last so a user-data trust root cannot replace an
    official key id with a different public key.
    """

    user_path = path or default_trust_roots_path()
    bundled = _read_roots_file(bundled_path or OFFICIAL_TRUST_ROOTS_PATH)
    user = _read_roots_file(user_path)
    roots = _empty_roots()
    _merge_public_keys(roots, user)
    _merge_public_keys(roots, bundled)
    return roots


def load_official_trust_roots(*, bundled_path: Path | None = None) -> dict[str, Any]:
    roots = _empty_roots()
    _merge_public_keys(roots, _read_roots_file(bundled_path or OFFICIAL_TRUST_ROOTS_PATH))
    return roots


def verify_signature(
    *,
    payload: bytes | str | None = None,
    signature: str | None,
    subject: str = "update artifact",
    bundle_sha256: str | None = None,
    pack_id: str | None = None,
    trust_roots: Mapping[str, Any] | None = None,
) -> None:
    """Verify an Ed25519 signature.

    ``bundle_sha256`` remains as a compatibility shim for callers that signed
    pack bundle digests before payload helpers existed.
    """

    if payload is None:
        if bundle_sha256 is None:
            raise TrustError(f"missing signature payload for {subject}")
        payload = pack_bundle_signature_payload(bundle_sha256)
        subject = subject if subject != "update artifact" else f"pack {pack_id or 'unknown'}"
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if not signature:
        raise TrustError(f"missing signature for {subject}")
    roots = trust_roots or load_trust_roots()
    _verify_ed25519(payload=payload, signature=signature, roots=roots, subject=subject)


def verify_index_signatures(
    index: Mapping[str, Any],
    *,
    subject: str,
    trust_roots: Mapping[str, Any] | None = None,
) -> None:
    signatures = index.get("signatures")
    if not isinstance(signatures, list) or not signatures:
        raise TrustError(f"missing signature for {subject}")
    payload = index_signature_payload(index)
    roots = trust_roots or load_trust_roots()
    errors: list[str] = []
    for item in signatures:
        signature = signature_string_from_entry(item)
        try:
            _verify_ed25519(payload=payload, signature=signature, roots=roots, subject=subject)
            return
        except TrustError as exc:
            errors.append(str(exc))
    raise TrustError(f"signature mismatch for {subject}: {'; '.join(errors)}")


def pack_bundle_signature_payload(bundle_sha256: str) -> bytes:
    return f"rumi-pack-bundle-v1:{bundle_sha256.lower()}".encode("utf-8")


def core_bundle_signature_payload(version: str, bundle_sha256: str) -> bytes:
    return f"rumi-core-bundle-v1:{version}:{bundle_sha256.lower()}".encode("utf-8")


def index_signature_payload(index: Mapping[str, Any]) -> bytes:
    unsigned = copy.deepcopy(dict(index))
    unsigned.pop("signatures", None)
    schema = str(unsigned.get("schema") or "unknown")
    return b"rumi-index-v1:" + schema.encode("utf-8") + b":" + canonical_json_bytes(unsigned)


def canonical_json_bytes(data: Mapping[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_ed25519(payload: bytes | str, key_id: str, private_key_b64_or_pem: str) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    private_key = _load_private_key(private_key_b64_or_pem)
    signature = private_key.sign(payload)
    return f"{ED25519_SCHEME}:{key_id}:{base64.b64encode(signature).decode('ascii')}"


def signature_entry(signature: str) -> dict[str, str]:
    scheme, key_id, signature_b64 = _parse_signature(signature)
    return {"scheme": scheme, "key_id": key_id, "signature": signature_b64}


def signature_string_from_entry(entry: Any) -> str | None:
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, Mapping):
        return None
    signature = entry.get("signature")
    if not isinstance(signature, str) or not signature:
        return None
    if signature.startswith(f"{ED25519_SCHEME}:"):
        return signature
    scheme = str(entry.get("scheme") or entry.get("signature_scheme") or ED25519_SCHEME)
    key_id = str(entry.get("key_id") or "")
    if not key_id:
        return None
    return f"{scheme}:{key_id}:{signature}"


def public_key_to_b64(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _empty_roots() -> dict[str, Any]:
    return {"schema": TRUST_SCHEMA, "ed25519_public_keys": {}}


def _read_roots_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _empty_roots()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return _empty_roots()
    return data if isinstance(data, dict) else _empty_roots()


def _merge_public_keys(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    keys = source.get("ed25519_public_keys")
    if not isinstance(keys, Mapping):
        keys = source.get("public_keys")
    if not isinstance(keys, Mapping):
        return
    target_keys = target.setdefault("ed25519_public_keys", {})
    for key_id, value in keys.items():
        if isinstance(key_id, str) and isinstance(value, str) and key_id and value:
            target_keys[key_id] = value


def _verify_ed25519(
    *,
    payload: bytes,
    signature: str | None,
    roots: Mapping[str, Any],
    subject: str,
) -> None:
    scheme, key_id, signature_b64 = _parse_signature(signature)
    if scheme != ED25519_SCHEME:
        raise TrustError(f"unsupported signature scheme for {subject}: {scheme}")
    keys = roots.get("ed25519_public_keys")
    if not isinstance(keys, Mapping) or key_id not in keys:
        raise TrustError(f"unknown trust root for {subject}: {key_id}")
    try:
        public_key = _load_public_key(str(keys[key_id]))
        signature_bytes = base64.b64decode(signature_b64, validate=True)
    except (TypeError, ValueError, binascii.Error) as exc:
        raise TrustError(f"invalid Ed25519 signature material for {subject}") from exc
    try:
        public_key.verify(signature_bytes, payload)
    except InvalidSignature as exc:
        raise TrustError(f"signature mismatch for {subject}") from exc


def _parse_signature(signature: str | None) -> tuple[str, str, str]:
    if not signature:
        raise TrustError("missing signature")
    parts = signature.split(":", 2)
    if len(parts) != 3 or not all(parts):
        raise TrustError("invalid signature format")
    return parts[0], parts[1], parts[2]


def _load_public_key(value: str) -> Ed25519PublicKey:
    text = value.strip()
    if text.startswith("-----BEGIN"):
        key = serialization.load_pem_public_key(text.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("not an Ed25519 public key")
        return key
    raw = base64.b64decode(text, validate=True)
    if len(raw) != 32:
        raise ValueError("Ed25519 public key must be 32 raw bytes")
    return Ed25519PublicKey.from_public_bytes(raw)


def _load_private_key(value: str) -> Ed25519PrivateKey:
    text = value.strip()
    if text.startswith("-----BEGIN"):
        key = serialization.load_pem_private_key(text.encode("utf-8"), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("not an Ed25519 private key")
        return key
    raw = base64.b64decode(text, validate=True)
    if len(raw) != 32:
        raise ValueError("Ed25519 private key must be 32 raw bytes")
    return Ed25519PrivateKey.from_private_bytes(raw)
