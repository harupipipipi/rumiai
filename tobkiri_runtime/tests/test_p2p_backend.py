from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.event import ExternalEvent  # noqa: E402
from domain.external.input_profile_engine import InputProfileEngine  # noqa: E402
from domain.external.input_profile_registry import InputProfileRegistry  # noqa: E402
from domain.p2p.identity import load_or_create_identity  # noqa: E402
from domain.p2p.inbound import handle_inbound_envelope  # noqa: E402
from domain.p2p.pairing import PairingManager  # noqa: E402
from domain.p2p.peer_store import PEER_PENDING, PeerStore  # noqa: E402
from domain.p2p.policy import P2PPolicy  # noqa: E402
from domain.p2p.protocol import make_envelope, sign_envelope  # noqa: E402
from domain.p2p.replay_guard import ReplayGuard  # noqa: E402
from domain.p2p.settings import P2PSettings  # noqa: E402


def _settings(tmp_path: Path, *, enabled: bool = True) -> P2PSettings:
    return P2PSettings(enabled=enabled, store_path=tmp_path, envelope_ttl_seconds=300, replay_ttl_seconds=600)


def _approved_peer(
    tmp_path: Path,
    *,
    peer_id: str = "peer-a",
    secret: str = "peer-secret",
    capabilities: list[str] | None = None,
    allowed_company_ids: list[str] | None = None,
):
    store = PeerStore(tmp_path)
    peer = store.approve_peer(
        peer_id,
        fingerprint=f"fp-{peer_id}",
        hmac_secret=secret,
        capabilities=capabilities if capabilities is not None else ["message"],
        allowed_company_ids=allowed_company_ids,
    )
    return store, peer


def _signed_message(peer, *, secret: str = "peer-secret", body=None, metadata=None, message_type: str = "message", timestamp_ms: int = 1_700_000_000_000):
    envelope = make_envelope(
        sender_id=peer.peer_id,
        recipient_id="local-node",
        message_type=message_type,
        body=body if isinstance(body, dict) else {"text": "hello"},
        metadata=metadata if isinstance(metadata, dict) else {},
        timestamp_ms=timestamp_ms,
    )
    return sign_envelope(envelope, secret)


def test_p2p_defaults_are_disabled_and_local_only(monkeypatch, tmp_path):
    monkeypatch.delenv("RUMI_DEFAULTSPACK_P2P_ENABLED", raising=False)
    monkeypatch.delenv("RUMI_DEFAULTSPACK_P2P_BIND_HOST", raising=False)
    monkeypatch.delenv("RUMI_DEFAULTSPACK_P2P_LAN_DISCOVERY", raising=False)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_P2P_STORE_PATH", str(tmp_path))

    settings = P2PSettings.from_env()

    assert settings.enabled is False
    assert settings.bind_host == "127.0.0.1"
    assert settings.lan_discovery is False
    assert settings.internet_relay is False

    from blocks.p2p.messages_send import run as send_run  # noqa: E402

    result = send_run({"peer_id": "peer-a", "text": "hi", "store_path": str(tmp_path)}, {})
    assert result["status"] == "error"
    assert result["error"]["code"] == "P2P_DISABLED"


def test_identity_persists_with_store_path_override(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_P2P_STORE_PATH", str(tmp_path))

    first = load_or_create_identity(label="local")
    second = load_or_create_identity()

    assert first.node_id == second.node_id
    assert first.fingerprint == second.fingerprint
    assert (tmp_path / "identity.json").exists()
    assert first.as_dict()["node_secret"] == "***"


def test_identity_rotate_changes_node_id_and_fingerprint_and_persists(tmp_path):
    from blocks.p2p.identity import run as identity_run  # noqa: E402

    first = identity_run({"store_path": str(tmp_path), "label": "local"}, {})["data"]["identity"]
    before_rotate = identity_run({"store_path": str(tmp_path)}, {})["data"]["identity"]

    rotated = identity_run({"store_path": str(tmp_path), "rotate": True}, {})["data"]["identity"]
    after_rotate = identity_run({"store_path": str(tmp_path)}, {})["data"]["identity"]
    persisted = load_or_create_identity(store_path=tmp_path)

    assert before_rotate["node_id"] == first["node_id"]
    assert before_rotate["fingerprint"] == first["fingerprint"]
    assert rotated["node_id"] != first["node_id"]
    assert rotated["fingerprint"] != first["fingerprint"]
    assert after_rotate["node_id"] == rotated["node_id"]
    assert after_rotate["fingerprint"] == rotated["fingerprint"]
    assert persisted.node_id == rotated["node_id"]
    assert persisted.fingerprint == rotated["fingerprint"]


def test_pairing_code_expiry_rejects_accept(tmp_path):
    manager = PairingManager(tmp_path)
    session = manager.start_pairing(peer_id="peer-a", ttl_seconds=1)

    result = manager.accept_pairing(session.code, peer_id="peer-a", now_ms=session.expires_at + 1)

    assert result["ok"] is False
    assert result["code"] == "PAIRING_EXPIRED"
    assert PeerStore(tmp_path).get_peer("peer-a") is None


def test_inbound_rejects_invalid_signature(tmp_path):
    store, peer = _approved_peer(tmp_path)
    envelope = _signed_message(peer, secret="wrong-secret")

    result = handle_inbound_envelope(
        envelope,
        settings=_settings(tmp_path),
        peer_store=store,
        replay_guard=ReplayGuard(tmp_path),
        current_time_ms=envelope["timestamp_ms"],
    )

    assert result["status"] == "error"
    assert result["code"] == "SIGNATURE_INVALID"


def test_inbound_rejects_unapproved_peer(tmp_path):
    store = PeerStore(tmp_path)
    peer = store.upsert_peer(
        "peer-a",
        fingerprint="fp-peer-a",
        hmac_secret="peer-secret",
        status=PEER_PENDING,
        capabilities=["message"],
    )
    envelope = _signed_message(peer)

    result = handle_inbound_envelope(
        envelope,
        settings=_settings(tmp_path),
        peer_store=store,
        replay_guard=ReplayGuard(tmp_path),
        current_time_ms=envelope["timestamp_ms"],
    )

    assert result["status"] == "denied"
    assert result["code"] == "PEER_UNAPPROVED"


def test_inbound_rejects_replay(tmp_path):
    store, peer = _approved_peer(tmp_path)
    envelope = _signed_message(peer)
    guard = ReplayGuard(tmp_path)

    first = handle_inbound_envelope(
        envelope,
        settings=_settings(tmp_path),
        peer_store=store,
        replay_guard=guard,
        current_time_ms=envelope["timestamp_ms"],
    )
    second = handle_inbound_envelope(
        envelope,
        settings=_settings(tmp_path),
        peer_store=store,
        replay_guard=guard,
        current_time_ms=envelope["timestamp_ms"],
    )

    assert first["status"] == "ok"
    assert second["status"] == "denied"
    assert second["code"] == "REPLAY_DETECTED"


@pytest.mark.parametrize(
    ("body", "metadata"),
    [
        ({"tool_name": "terminal_exec"}, {}),
        ({"tool": "file_write"}, {}),
        ({"selected_tools": ["git_push"]}, {}),
        ({"requested_tool": "browser_computer"}, {}),
        ({"approval_granted": True}, {}),
        ({}, {"approved": True}),
        ({"write_actions_require_approval": False}, {}),
        ({"allow_shell": True}, {}),
    ],
)
def test_policy_denies_privileged_tool_and_approval_claims(tmp_path, body, metadata):
    store, peer = _approved_peer(tmp_path)
    envelope = make_envelope(sender_id=peer.peer_id, body=body, metadata=metadata)

    decision = P2PPolicy(store).evaluate(envelope, peer=peer)

    assert decision.allowed is False
    assert decision.code == "PRIVILEGED_CLAIM_DENIED"


def test_policy_enforces_capabilities_and_company_allowlist(tmp_path):
    store, peer = _approved_peer(tmp_path, capabilities=["external_event"], allowed_company_ids=["company-a"])
    message = make_envelope(sender_id=peer.peer_id, body={"text": "hello"})
    company = make_envelope(sender_id=peer.peer_id, body={"text": "hello", "company_id": "company-b"}, message_type="external_event")

    message_decision = P2PPolicy(store).evaluate(message, peer=peer)
    company_decision = P2PPolicy(store).evaluate(company, peer=peer)

    assert message_decision.allowed is False
    assert message_decision.code == "CAPABILITY_DENIED"
    assert company_decision.allowed is False
    assert company_decision.code == "COMPANY_DENIED"


def test_inbound_normalizes_to_p2p_external_event_and_profile(tmp_path):
    store, peer = _approved_peer(tmp_path, allowed_company_ids=["company-a"])
    envelope = _signed_message(
        peer,
        body={"text": "hello from peer", "company_id": "company-a", "company_channel_id": "general"},
    )
    appended = []

    result = handle_inbound_envelope(
        envelope,
        context={"company_append_message": appended.append},
        settings=_settings(tmp_path),
        peer_store=store,
        replay_guard=ReplayGuard(tmp_path),
        current_time_ms=envelope["timestamp_ms"],
    )
    event = ExternalEvent.from_dict(result["event"])
    profile = InputProfileRegistry(DEFAULTSPACK_ROOT).get("p2p.default")
    input_envelope = InputProfileEngine(profile).to_envelope(event)

    assert result["status"] == "ok"
    assert event.provider == "p2p"
    assert event.verified is True
    assert event.payload["body"]["text"] == "hello from peer"
    assert event.scope.type == "company"
    assert event.scope.id == "company-a"
    assert event.metadata["p2p"]["peer_id"] == "peer-a"
    assert input_envelope.input == "hello from peer"
    assert input_envelope.source["provider"] == "p2p"
    assert appended[0]["company_id"] == "company-a"
    assert appended[0]["channel_id"] == "general"
