from __future__ import annotations

import base64
import json
import os
import secrets
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


TOKEN_DELIVERY_ALG = "X25519-HKDF-SHA256-AES-256-GCM"
TOKEN_DELIVERY_VERSION = 1
_HKDF_SALT = b"rumi-mobile-token-delivery-v1"


def encrypt_token_delivery(
    payload: dict[str, Any],
    recipient_public_key: str,
    *,
    pairing_id: str,
    device_id: str,
) -> dict[str, Any]:
    public_key = _decode_x25519_public_key(recipient_public_key)
    delivery_id = "tdv_" + secrets.token_urlsafe(18)
    ephemeral_private = x25519.X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    shared_secret = ephemeral_private.exchange(public_key)
    aad = _aad(pairing_id=pairing_id, device_id=device_id, delivery_id=delivery_id)
    key = _derive_key(shared_secret, pairing_id=pairing_id, device_id=device_id, delivery_id=delivery_id)
    nonce = os.urandom(12)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encrypted = AESGCM(key).encrypt(nonce, plaintext, aad)
    ciphertext, tag = encrypted[:-16], encrypted[-16:]
    return {
        "version": TOKEN_DELIVERY_VERSION,
        "delivery_id": delivery_id,
        "alg": TOKEN_DELIVERY_ALG,
        "ephemeral_public_key": "x25519:" + _b64url(ephemeral_public),
        "nonce": _b64url(nonce),
        "ciphertext": _b64url(ciphertext),
        "tag": _b64url(tag),
        "aad": _b64url(aad),
    }


def _decode_x25519_public_key(value: str) -> x25519.X25519PublicKey:
    text = str(value or "").strip()
    if text.startswith("x25519:"):
        text = text[len("x25519:") :]
    raw = _unb64url(text)
    if len(raw) != 32:
        raise ValueError("device encryption public key must be an X25519 public key")
    return x25519.X25519PublicKey.from_public_bytes(raw)


def _derive_key(shared_secret: bytes, *, pairing_id: str, device_id: str, delivery_id: str) -> bytes:
    info = f"{pairing_id}:{device_id}:{delivery_id}".encode("utf-8")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=info,
    ).derive(shared_secret)


def _aad(*, pairing_id: str, device_id: str, delivery_id: str) -> bytes:
    return f"rumi-mobile-token-delivery:v1:{pairing_id}:{device_id}:{delivery_id}".encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(value: str) -> bytes:
    text = str(value or "").strip()
    return base64.urlsafe_b64decode(text + "=" * ((4 - len(text) % 4) % 4))
