from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.asymmetric import x25519

from .errors import ContinuityError, CREDENTIAL_SCOPE_DENIED
from .models import CredentialEnvelope, canonical_json, content_hash
from .node_registry import (
    _b64,
    _unb64,
    load_ed25519_private,
    load_ed25519_public,
    load_x25519_private,
    load_x25519_public,
)
from .store import JsonFileStore, default_continuity_dir


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _future(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _shared_key(private_key_b64: str, public_key_b64: str, *, salt: bytes | None = None) -> bytes:
    private = load_x25519_private(private_key_b64)
    public = load_x25519_public(public_key_b64)
    shared = private.exchange(public)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"rumi-continuity-credential-envelope-v1",
    ).derive(shared)


class CredentialEnvelopeService:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_continuity_dir()
        self.store = JsonFileStore(self.root / "credential_envelopes.json")

    def create(
        self,
        *,
        secret_value: str,
        source_node: dict[str, Any],
        source_key_material: dict[str, str],
        destination_node: dict[str, Any],
        provider_id: str,
        api_id: str,
        allowed_model_ids: tuple[str, ...],
        base_url: str | None,
        permissions: tuple[str, ...] = ("model.invoke", "api_key.use"),
        ttl_seconds: int = 3600,
        max_requests: int | None = None,
    ) -> CredentialEnvelope:
        secret_text = str(secret_value or "")
        if not secret_text:
            raise ContinuityError("Provider credential is unavailable.", "CREDENTIAL_UNAVAILABLE", 409)
        allowed = tuple(str(item) for item in allowed_model_ids if str(item or "").strip())
        if not allowed:
            raise ContinuityError("Credential envelope requires at least one scoped model.", CREDENTIAL_SCOPE_DENIED, 400)
        # A source-local one-shot X25519 key avoids reusing the source device key
        # as the ECDH sender for every delegated credential.
        ephemeral_private = x25519.X25519PrivateKey.generate()
        ephemeral_private_b64 = _b64(ephemeral_private.private_bytes_raw())
        ephemeral_public = _b64(ephemeral_private.public_key().public_bytes_raw())
        nonce = os.urandom(12)
        salt = os.urandom(16)
        key = _shared_key(ephemeral_private_b64, str(destination_node.get("device_public_key") or ""), salt=salt)
        envelope_id = "cred-" + uuid.uuid4().hex[:18]
        base_url_hash = content_hash({"base_url": base_url or ""})
        plaintext = canonical_json(
            {
                "secret": secret_text,
                "provider_id": provider_id,
                "api_id": api_id,
                "allowed_model_ids": allowed,
                "allowed_base_url_hash": base_url_hash,
                "permissions": permissions,
                "envelope_id": envelope_id,
            }
        ).encode("utf-8")
        aad = canonical_json(
            {
                "envelope_id": envelope_id,
                "source_node_id": source_node.get("node_id"),
                "destination_node_id": destination_node.get("node_id"),
                "provider_id": provider_id,
                "api_id": api_id,
                "allowed_model_ids": allowed,
                "allowed_base_url_hash": base_url_hash,
            }
        ).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
        signing_private = load_ed25519_private(source_key_material["signing_private_key"])
        envelope = CredentialEnvelope(
            envelope_id=envelope_id,
            source_node_id=str(source_node.get("node_id") or ""),
            destination_node_id=str(destination_node.get("node_id") or ""),
            provider_id=provider_id,
            api_id=api_id,
            allowed_model_ids=allowed,
            allowed_base_url_hash=base_url_hash,
            permissions=tuple(permissions),
            expires_at=_future(ttl_seconds),
            created_at=utc_now(),
            ephemeral_public_key=ephemeral_public,
            nonce=_b64(nonce),
            ciphertext=_b64(salt + ciphertext),
            source_signing_public_key=str(source_key_material.get("signing_public_key") or source_node.get("signing_public_key") or ""),
            source_signature="",
            max_requests=max_requests,
        )
        signature = signing_private.sign(canonical_json(envelope.unsigned_payload()).encode("utf-8"))
        envelope = CredentialEnvelope(**{**envelope.as_dict(), "source_signature": _b64(signature)})
        self.save(envelope)
        return envelope

    def save(self, envelope: CredentialEnvelope) -> None:
        def _update(data: dict[str, Any]):
            envelopes = data.setdefault("envelopes", {})
            envelopes[envelope.envelope_id] = envelope.as_dict()
            return data, None

        self.store.update(_update)

    def get(self, envelope_id: str) -> dict[str, Any] | None:
        data = self.store.read()
        envelopes = data.get("envelopes") if isinstance(data.get("envelopes"), dict) else {}
        envelope = envelopes.get(str(envelope_id))
        return dict(envelope) if isinstance(envelope, dict) else None

    def unwrap(self, envelope_payload: dict[str, Any], *, destination_private_key: str) -> dict[str, Any]:
        envelope = CredentialEnvelope(**envelope_payload)
        public = load_ed25519_public(envelope.source_signing_public_key)
        try:
            public.verify(_unb64(envelope.source_signature), canonical_json(envelope.unsigned_payload()).encode("utf-8"))
        except InvalidSignature as exc:
            raise ContinuityError("Credential envelope signature is invalid.", "CREDENTIAL_SIGNATURE_INVALID", 403) from exc
        raw_ciphertext = _unb64(envelope.ciphertext)
        salt, ciphertext = raw_ciphertext[:16], raw_ciphertext[16:]
        key = _shared_key(destination_private_key, envelope.ephemeral_public_key, salt=salt)
        aad = canonical_json(
            {
                "envelope_id": envelope.envelope_id,
                "source_node_id": envelope.source_node_id,
                "destination_node_id": envelope.destination_node_id,
                "provider_id": envelope.provider_id,
                "api_id": envelope.api_id,
                "allowed_model_ids": envelope.allowed_model_ids,
                "allowed_base_url_hash": envelope.allowed_base_url_hash,
            }
        ).encode("utf-8")
        plaintext = AESGCM(key).decrypt(_unb64(envelope.nonce), ciphertext, aad)
        import json

        return json.loads(plaintext.decode("utf-8"))
