from __future__ import annotations

import base64
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


FAKE_SECRET = "fake-provider-key-for-issue-994-tests-only"
ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def _keys():
    signing_private = ed25519.Ed25519PrivateKey.generate()
    encryption_private = x25519.X25519PrivateKey.generate()
    signing_public = signing_private.public_key().public_bytes_raw()
    encryption_public = encryption_private.public_key().public_bytes_raw()
    return signing_private, encryption_private, "ed25519:" + _b64url(signing_public), "x25519:" + _b64url(encryption_public)


def _setup(monkeypatch, tmp_path: Path):
    from blocks.mobile import credentials
    from domain.p2p.device_store import DeviceStore

    monkeypatch.setenv("RUMI_MOBILE_CREDENTIAL_TRANSFER", "1")
    monkeypatch.setattr(credentials, "read_provider_api_key", lambda provider_id, api_id: FAKE_SECRET)
    monkeypatch.setattr(credentials, "provider_api_metadata", lambda provider_id, api_id: {
        "name": "Fake Provider",
        "base_url": "https://invalid.example.test/v1",
        "default_model": "fake-model",
    })
    signing_private, encryption_private, signing_public, encryption_public = _keys()
    DeviceStore(tmp_path).issue_tokens(
        "device-recipient",
        label="Test Phone",
        public_key=signing_public,
        encryption_public_key=encryption_public,
        scopes=["credentials.request"],
        pairing_id="pair-fake",
    )
    return credentials, signing_private, encryption_private


def _create_and_confirm(credentials, tmp_path: Path):
    created = credentials.run({
        "action": "create",
        "store_path": str(tmp_path),
        "device_id": "device-recipient",
        "provider_id": "fake-provider",
        "api_id": "fake-account",
        "provider_label": "Fake Provider",
    })
    assert created["status"] == "ok"
    transfer = created["data"]["transfer"]
    confirmed = credentials.run({
        "action": "confirm",
        "store_path": str(tmp_path),
        "transfer_id": transfer["transfer_id"],
        "device_id": transfer["device_id"],
        "provider_id": transfer["provider_id"],
        "api_id": transfer["api_id"],
        "user_confirmed": True,
    })
    assert confirmed["status"] == "ok"
    return confirmed["data"]["transfer"]


def _sign(transfer: dict, signing_private) -> str:
    payload = {
        "transfer_id": transfer["transfer_id"],
        "device_id": transfer["device_id"],
        "provider_id": transfer["provider_id"],
        "api_id": transfer["api_id"],
        "expires_at": transfer["expires_at"],
        "challenge": transfer["redemption_challenge"],
    }
    message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return _b64url(signing_private.sign(hashlib.sha256(message).digest()))


def _decrypt(envelope: dict, transfer: dict, encryption_private) -> dict:
    ephemeral = x25519.X25519PublicKey.from_public_bytes(
        _unb64url(envelope["ephemeral_public_key"].removeprefix("x25519:"))
    )
    shared = encryption_private.exchange(ephemeral)
    info = f"{transfer['transfer_id']}:{transfer['device_id']}:{transfer['expires_at']}".encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"rumi-provider-credential-transfer-v1", info=info).derive(shared)
    encrypted = _unb64url(envelope["ciphertext"]) + _unb64url(envelope["tag"])
    clear = AESGCM(key).decrypt(_unb64url(envelope["nonce"]), encrypted, _unb64url(envelope["aad"]))
    return json.loads(clear)


def test_secure_transfer_requires_confirmation_and_never_exposes_plaintext(monkeypatch, tmp_path):
    credentials, signing_private, encryption_private = _setup(monkeypatch, tmp_path)
    transfer = _create_and_confirm(credentials, tmp_path)

    public_json = json.dumps(transfer)
    storage_json = (tmp_path / "credential_transfers.json").read_text()
    assert FAKE_SECRET not in public_json
    assert FAKE_SECRET not in storage_json
    assert "ciphertext" not in public_json
    assert transfer["status"] == "pending"

    listed = credentials.run(
        {"action": "list", "store_path": str(tmp_path)},
        {"_authenticated_device_id": "device-recipient"},
    )
    mobile_transfer = listed["data"]["transfers"][0]
    redeemed = credentials.run(
        {
            "action": "redeem",
            "store_path": str(tmp_path),
            "transfer_id": transfer["transfer_id"],
            "signature": _sign(mobile_transfer, signing_private),
        },
        {"_authenticated_device_id": "device-recipient"},
    )
    assert redeemed["status"] == "ok"
    payload = _decrypt(redeemed["data"]["envelope"], transfer, encryption_private)
    assert payload["api_key"] == FAKE_SECRET
    assert payload["provider_id"] == "fake-provider"


def test_replay_and_multiple_scans_are_rejected(monkeypatch, tmp_path):
    credentials, signing_private, _ = _setup(monkeypatch, tmp_path)
    transfer = _create_and_confirm(credentials, tmp_path)
    listed = credentials.run(
        {"action": "list", "store_path": str(tmp_path)},
        {"_authenticated_device_id": "device-recipient"},
    )["data"]["transfers"][0]
    request = {
        "action": "redeem",
        "store_path": str(tmp_path),
        "transfer_id": transfer["transfer_id"],
        "signature": _sign(listed, signing_private),
    }
    first = credentials.run(request, {"_authenticated_device_id": "device-recipient"})
    second = credentials.run(request, {"_authenticated_device_id": "device-recipient"})
    assert first["status"] == "ok"
    assert second["status"] == "error"
    assert "envelope" not in second.get("data", {})


def test_wrong_recipient_tampering_and_changed_confirmation_are_rejected(monkeypatch, tmp_path):
    credentials, signing_private, _ = _setup(monkeypatch, tmp_path)
    transfer = _create_and_confirm(credentials, tmp_path)
    listed = credentials.run(
        {"action": "list", "store_path": str(tmp_path)},
        {"_authenticated_device_id": "device-recipient"},
    )["data"]["transfers"][0]
    wrong_device = credentials.run(
        {
            "action": "redeem",
            "store_path": str(tmp_path),
            "transfer_id": transfer["transfer_id"],
            "signature": _sign(listed, signing_private),
        },
        {"_authenticated_device_id": "device-attacker"},
    )
    assert wrong_device["status"] == "error"
    bad_signature = credentials.run(
        {
            "action": "redeem",
            "store_path": str(tmp_path),
            "transfer_id": transfer["transfer_id"],
            "signature": _b64url(b"tampered-signature"),
        },
        {"_authenticated_device_id": "device-recipient"},
    )
    assert bad_signature["status"] == "error"

    created = credentials.run({
        "action": "create", "store_path": str(tmp_path), "device_id": "device-recipient",
        "provider_id": "fake-provider", "api_id": "fake-account",
    })["data"]["transfer"]
    changed = credentials.run({
        "action": "confirm", "store_path": str(tmp_path), "transfer_id": created["transfer_id"],
        "device_id": "device-attacker", "provider_id": "fake-provider", "api_id": "fake-account",
        "user_confirmed": True,
    })
    assert changed["status"] == "error"


def test_expiry_revoke_reject_cancel_and_device_compromise_boundaries(monkeypatch, tmp_path):
    credentials, _, _ = _setup(monkeypatch, tmp_path)
    transfer = _create_and_confirm(credentials, tmp_path)
    from domain.p2p import credential_transfer as transfer_module

    monkeypatch.setattr(transfer_module, "_now_ms", lambda: transfer["expires_at"] + 1)
    status = credentials.run({
        "action": "status", "store_path": str(tmp_path), "transfer_id": transfer["transfer_id"],
    })
    assert status["data"]["transfer"]["status"] == "expired"
    assert credentials.run(
        {"action": "list", "store_path": str(tmp_path)},
        {"_authenticated_device_id": "device-recipient"},
    )["data"]["transfers"] == []

    monkeypatch.undo()
    credentials, _, _ = _setup(monkeypatch, tmp_path / "states")
    for target in ("rejected", "cancelled", "revoked"):
        pending = _create_and_confirm(credentials, tmp_path / "states")
        action = {"rejected": "reject", "cancelled": "cancel", "revoked": "revoke"}[target]
        context = {"_authenticated_device_id": "device-recipient"} if target == "rejected" else None
        result = credentials.run({
            "action": action,
            "store_path": str(tmp_path / "states"),
            "transfer_id": pending["transfer_id"],
        }, context)
        assert result["data"]["transfer"]["status"] == target


def test_client_material_and_diagnostics_fields_are_rejected(monkeypatch, tmp_path):
    credentials, _, _ = _setup(monkeypatch, tmp_path)
    for field in ("api_key", "secret", "plaintext", "ciphertext", "nonce"):
        result = credentials.run({
            "action": "create", "store_path": str(tmp_path), "device_id": "device-recipient",
            "provider_id": "fake-provider", "api_id": "fake-account", field: FAKE_SECRET,
        })
        assert result["status"] == "error"
        assert FAKE_SECRET not in json.dumps(result)


def test_ack_requires_authenticated_recipient(monkeypatch, tmp_path):
    credentials, signing_private, _ = _setup(monkeypatch, tmp_path)
    transfer = _create_and_confirm(credentials, tmp_path)
    listed = credentials.run(
        {"action": "list", "store_path": str(tmp_path)},
        {"_authenticated_device_id": "device-recipient"},
    )["data"]["transfers"][0]
    credentials.run(
        {"action": "redeem", "store_path": str(tmp_path), "transfer_id": transfer["transfer_id"], "signature": _sign(listed, signing_private)},
        {"_authenticated_device_id": "device-recipient"},
    )
    unauthenticated = credentials.run({
        "action": "ack", "store_path": str(tmp_path), "transfer_id": transfer["transfer_id"],
    })
    assert unauthenticated["status"] == "error"
    acknowledged = credentials.run(
        {"action": "ack", "store_path": str(tmp_path), "transfer_id": transfer["transfer_id"]},
        {"_authenticated_device_id": "device-recipient"},
    )
    assert acknowledged["data"]["transfer"]["status"] == "completed"


def test_recipient_and_provider_display_are_backend_authoritative(monkeypatch, tmp_path):
    credentials, _, _ = _setup(monkeypatch, tmp_path)
    created = credentials.run({
        "action": "create",
        "store_path": str(tmp_path),
        "device_id": "device-recipient",
        "profile_id": "attacker-profile",
        "provider_id": "fake-provider",
        "api_id": "fake-account",
        "provider_label": "Spoofed Provider",
    })
    assert created["status"] == "ok"
    transfer = created["data"]["transfer"]
    assert transfer["profile_id"] == "default"
    assert transfer["provider_label"] == "Fake Provider"
    assert "Spoofed" not in json.dumps(transfer)


def test_envelope_tampering_fails_authenticated_decryption(monkeypatch, tmp_path):
    credentials, signing_private, encryption_private = _setup(monkeypatch, tmp_path)
    transfer = _create_and_confirm(credentials, tmp_path)
    listed = credentials.run(
        {"action": "list", "store_path": str(tmp_path)},
        {"_authenticated_device_id": "device-recipient"},
    )["data"]["transfers"][0]
    redeemed = credentials.run(
        {"action": "redeem", "store_path": str(tmp_path), "transfer_id": transfer["transfer_id"], "signature": _sign(listed, signing_private)},
        {"_authenticated_device_id": "device-recipient"},
    )
    envelope = redeemed["data"]["envelope"]
    envelope["ciphertext"] = ("A" if envelope["ciphertext"][0] != "A" else "B") + envelope["ciphertext"][1:]
    with pytest.raises(Exception):
        _decrypt(envelope, transfer, encryption_private)


def test_redemption_canonical_message_cross_language_vector():
    from domain.p2p.credential_transfer import redemption_message

    record = {
        "transfer_id": "ctr_vector",
        "device_id": "device-vector",
        "provider_id": "fake-provider",
        "api_id": "fake-account",
        "expires_at": 1893456000000,
        "redemption_challenge": "rch_vector",
    }
    message = redemption_message(record)
    assert message == (
        b'{"api_id":"fake-account","challenge":"rch_vector",'
        b'"device_id":"device-vector","expires_at":1893456000000,'
        b'"provider_id":"fake-provider","transfer_id":"ctr_vector"}'
    )
    assert hashlib.sha256(message).hexdigest() == "0ce091bc43b73881bcb71950abe6a8c44672224f819fd15cb183da80de405eda"


def test_accepted_is_delivered_and_cannot_be_revoked(monkeypatch, tmp_path):
    credentials, signing_private, _ = _setup(monkeypatch, tmp_path)
    transfer = _create_and_confirm(credentials, tmp_path)
    listed = credentials.run(
        {"action": "list", "store_path": str(tmp_path)},
        {"_authenticated_device_id": "device-recipient"},
    )["data"]["transfers"][0]
    accepted = credentials.run(
        {"action": "redeem", "store_path": str(tmp_path), "transfer_id": transfer["transfer_id"], "signature": _sign(listed, signing_private)},
        {"_authenticated_device_id": "device-recipient"},
    )
    assert accepted["data"]["transfer"]["status"] == "accepted"
    revoked = credentials.run({
        "action": "revoke", "store_path": str(tmp_path), "transfer_id": transfer["transfer_id"],
    })
    assert revoked["status"] == "error"
    assert credentials.run({
        "action": "status", "store_path": str(tmp_path), "transfer_id": transfer["transfer_id"],
    })["data"]["transfer"]["status"] == "accepted"


def test_replay_failure_audit_is_sanitized_and_success_is_not_duplicated(monkeypatch, tmp_path):
    credentials, signing_private, _ = _setup(monkeypatch, tmp_path)
    events = []
    monkeypatch.setattr(credentials, "audit_event", lambda context, action, fields: events.append((action, fields)))
    transfer = _create_and_confirm(credentials, tmp_path)
    listed = credentials.run(
        {"action": "list", "store_path": str(tmp_path)},
        {"_authenticated_device_id": "device-recipient"},
    )["data"]["transfers"][0]
    request = {
        "action": "redeem",
        "store_path": str(tmp_path),
        "transfer_id": transfer["transfer_id"],
        "signature": _sign(listed, signing_private),
    }
    assert credentials.run(request, {"_authenticated_device_id": "device-recipient"})["status"] == "ok"
    assert credentials.run(request, {"_authenticated_device_id": "device-recipient"})["status"] == "error"

    actions = [action for action, _ in events]
    assert actions.count("credential_transfer.accepted") == 1
    assert actions.count("credential_transfer.redeem_failed") == 1
    failure = next(fields for action, fields in events if action == "credential_transfer.redeem_failed")
    assert failure == {
        "success": False,
        "transfer_id": transfer["transfer_id"],
        "outcome": "invalid_state",
    }
    assert FAKE_SECRET not in json.dumps(events)


def test_attacker_controlled_transfer_id_is_omitted_from_audit(monkeypatch, tmp_path):
    credentials, _, _ = _setup(monkeypatch, tmp_path)
    events = []
    monkeypatch.setattr(credentials, "audit_event", lambda context, action, fields: events.append((action, fields)))
    hostile_id = FAKE_SECRET + "-as-transfer-id"
    result = credentials.run({"action": "status", "store_path": str(tmp_path), "transfer_id": hostile_id})
    assert result["status"] == "error"
    serialized = json.dumps(events)
    assert hostile_id not in serialized
    assert FAKE_SECRET not in serialized
    assert events == [("credential_transfer.status_failed", {"success": False, "outcome": "not_found"})]


def test_wrong_recipient_proof_has_specialized_sanitized_error(monkeypatch, tmp_path):
    credentials, _, _ = _setup(monkeypatch, tmp_path)
    transfer = _create_and_confirm(credentials, tmp_path)
    result = credentials.run(
        {
            "action": "redeem",
            "store_path": str(tmp_path),
            "transfer_id": transfer["transfer_id"],
            "signature": _b64url(b"fake-invalid-proof"),
        },
        {"_authenticated_device_id": "device-recipient"},
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "RECIPIENT_PROOF_REJECTED"
    assert FAKE_SECRET not in json.dumps(result)


def test_expiry_audit_is_claimed_exactly_once_across_status_and_list(monkeypatch, tmp_path):
    credentials, _, _ = _setup(monkeypatch, tmp_path)
    events = []
    monkeypatch.setattr(credentials, "audit_event", lambda context, action, fields: events.append((action, fields)))
    transfer = _create_and_confirm(credentials, tmp_path)
    from domain.p2p import credential_transfer as transfer_module

    monkeypatch.setattr(transfer_module, "_now_ms", lambda: transfer["expires_at"] + 1)
    status_request = {"action": "status", "store_path": str(tmp_path), "transfer_id": transfer["transfer_id"]}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: credentials.run(status_request), range(16)))
    assert all(result["data"]["transfer"]["status"] == "expired" for result in results)
    for _ in range(2):
        credentials.run(
            {"action": "list", "store_path": str(tmp_path)},
            {"_authenticated_device_id": "device-recipient"},
        )
    expiry_events = [fields for action, fields in events if action == "credential_transfer.expired"]
    assert len(expiry_events) == 1
    assert expiry_events[0]["transfer_id"] == transfer["transfer_id"]
    assert FAKE_SECRET not in json.dumps(expiry_events)
