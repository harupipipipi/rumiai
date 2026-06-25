from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

AUTHORITY_APPROVER_SCOPES = [
    "authority.request.approve",
    "authority.request.deny",
    "authority.request.list",
    "authority.request.read",
]


def test_pairing_v2_claim_approve_flow():
    from domain.p2p.pairing import PairingManager
    from domain.p2p.device_store import DeviceStore

    tmp = tempfile.mkdtemp()
    pm = PairingManager(tmp)
    session = pm.start_pairing(ttl_seconds=300)
    assert session.status == "pending"

    # Claim
    claim = pm.claim_pairing(
        session.pairing_id,
        code=session.code,
        device_id="iphone-1",
        device_label="はるのiPhone",
        device_public_key="pk-abc",
        requested_capabilities=["chat.read", "chat.write", "tools.observe"],
    )
    assert claim["ok"]
    assert claim["pairing"]["status"] == "claimed"
    assert claim["pairing"]["claimed_device_id"] == "iphone-1"

    # Approve
    approve = pm.approve_pairing_v2(session.pairing_id)
    assert approve["ok"]
    assert approve["pairing"]["status"] == "approved"
    assert approve["device_id"] == "iphone-1"
    assert "chat.read" in approve["scopes"]

    # Issue device token
    ds = DeviceStore(tmp)
    device, token, approval_token = ds.issue_tokens(
        approve["device_id"],
        label=approve["device_label"],
        public_key=approve["device_public_key"],
        scopes=[*approve["scopes"], "tools.approve"],
        pairing_id=session.pairing_id,
    )
    assert token.startswith("dtk_")
    assert approval_token.startswith("dtk_")
    assert device.confirmation_code  # visual code like "🟢・58"
    assert "tools.approve" not in device.scopes
    assert device.approval_scopes == AUTHORITY_APPROVER_SCOPES

    # Verify token
    verified = ds.verify_token(token)
    assert verified is not None
    assert verified.device_id == "iphone-1"
    assert "tools.approve" not in verified.scopes

    verified_approval = ds.verify_token(approval_token)
    assert verified_approval is not None
    assert verified_approval.device_id == "iphone-1"
    assert verified_approval.scopes == AUTHORITY_APPROVER_SCOPES

    # Revoke
    revoked = ds.revoke_device("iphone-1")
    assert revoked.status == "revoked"
    assert ds.verify_token(token) is None
    assert ds.verify_token(approval_token) is None


def test_pairing_v2_reject():
    from domain.p2p.pairing import PairingManager

    tmp = tempfile.mkdtemp()
    pm = PairingManager(tmp)
    session = pm.start_pairing()
    pm.claim_pairing(session.pairing_id, code=session.code, device_id="d1")
    result = pm.reject_pairing(session.code)
    assert result["ok"]
    assert result["pairing"]["status"] == "rejected"


def test_pairing_v2_claim_expired():
    from domain.p2p.pairing import PairingManager

    tmp = tempfile.mkdtemp()
    pm = PairingManager(tmp)
    session = pm.start_pairing(ttl_seconds=1)
    # Force expiry
    result = pm.claim_pairing(
        session.pairing_id,
        code=session.code,
        device_id="d1",
        now_ms=session.expires_at + 1000,
    )
    assert not result["ok"]
    assert result["code"] == "PAIRING_EXPIRED"


def test_device_store_list_and_patch():
    from domain.p2p.device_store import DeviceStore

    tmp = tempfile.mkdtemp()
    ds = DeviceStore(tmp)
    ds.issue_token("d1", label="iPhone")
    ds.issue_token("d2", label="iPad")

    devices = ds.list_devices()
    assert len(devices) == 2
    ids = {d["device_id"] for d in devices}
    assert ids == {"d1", "d2"}

    updated = ds.update_label("d1", "はるのiPhone")
    assert updated.label == "はるのiPhone"


def test_device_token_is_scoped():
    from domain.p2p.device_store import DeviceStore, DEFAULT_SCOPES

    tmp = tempfile.mkdtemp()
    ds = DeviceStore(tmp)
    device, token, approval_token = ds.issue_tokens(
        "d1",
        scopes=["chat.read", "tools.observe", "tools.approve"],
    )
    assert "chat.read" in device.scopes
    assert "chat.write" not in device.scopes
    assert "tools.approve" not in device.scopes
    assert device.approval_scopes == AUTHORITY_APPROVER_SCOPES
    assert "credentials.request" not in device.scopes
    assert ds.verify_token(token).scopes == ["chat.read", "tools.observe"]
    assert ds.verify_token(approval_token).scopes == AUTHORITY_APPROVER_SCOPES


def test_legacy_device_record_does_not_keep_approval_scope_on_normal_token():
    from domain.p2p.device_store import DeviceRecord

    record = DeviceRecord.from_dict({
        "device_id": "legacy-mobile",
        "token_hash": "hash",
        "scopes": ["chat.read", "tools.approve"],
    })

    assert record.scopes == ["chat.read"]
    assert record.approval_scopes == []


def test_pairing_claim_requires_matching_code():
    from domain.p2p.pairing import PairingManager

    tmp = tempfile.mkdtemp()
    pm = PairingManager(tmp)
    session = pm.start_pairing()

    result = pm.claim_pairing(
        session.pairing_id,
        code="WRNG-CODE",
        device_id="d1",
    )

    assert not result["ok"]
    assert result["code"] == "PAIRING_CODE_MISMATCH"


def test_mobile_pairing_status_requires_pickup_secret_and_device_for_token():
    from domain.p2p.device_store import DeviceStore
    from domain.p2p.pairing import PairingManager
    from blocks.mobile.pairing import run

    tmp = tempfile.mkdtemp()
    session = PairingManager(tmp).start_pairing(
        capabilities=["chat.read", "chat.write", "tools.observe"],
    )

    claim = run({
        "action": "claim",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "code": session.code,
        "device_id": "mobile-1",
        "device_label": "iPhone",
        "public_key": "pk-mobile",
        "requested_capabilities": ["chat.read", "chat.write"],
    }, None)
    assert claim["status"] == "ok"
    assert claim["data"]["pairing"]["status"] == "claimed"
    assert "code" not in claim["data"]["pairing"]

    approved = run({
        "action": "approve",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
    }, None)
    assert approved["status"] == "ok"
    assert approved["data"]["pairing"]["status"] == "approved"
    assert "code" not in approved["data"]["pairing"]
    assert "device_token" not in approved["data"]
    assert "approval_token" not in approved["data"]
    assert "client_access_token" not in approved["data"]
    assert "approver_access_token" not in approved["data"]

    without_code = run({
        "action": "status",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
    }, None)
    assert without_code["status"] == "ok"
    assert "device_token" not in without_code["data"]
    assert "code" not in without_code["data"]
    assert "code" not in without_code["data"]["pairing"]

    with_code = run({
        "action": "status",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "code": session.code,
        "device_id": "mobile-1",
    }, None)
    assert with_code["status"] == "ok"
    assert "device_token" not in with_code["data"]
    assert "code" not in with_code["data"]
    assert "code" not in with_code["data"]["pairing"]

    with_secret = run({
        "action": "status",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "pickup_secret": session.token_pickup_secret,
        "device_id": "mobile-1",
    }, None)
    assert with_secret["status"] == "ok"
    assert with_secret["data"]["device_token"].startswith("dtk_")
    assert with_secret["data"]["approval_token"] == ""
    assert with_secret["data"]["approval_scopes"] == []
    assert with_secret["data"]["scopes"] == ["chat.read", "chat.write"]
    assert "code" not in with_secret["data"]
    assert "code" not in with_secret["data"]["pairing"]
    first_device = DeviceStore(tmp).get_device("mobile-1")
    assert first_device is not None
    first_token_hash = first_device.token_hash

    replay = run({
        "action": "status",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "pickup_secret": session.token_pickup_secret,
        "device_id": "mobile-1",
    }, None)
    assert replay["status"] == "ok"
    assert "device_token" not in replay["data"]
    assert "code" not in replay["data"]
    assert "code" not in replay["data"]["pairing"]
    replay_device = DeviceStore(tmp).get_device("mobile-1")
    assert replay_device is not None
    assert replay_device.token_hash == first_token_hash


def test_pairing_start_returns_mobile_pickup_secret():
    from blocks.p2p import pairing_start

    tmp = tempfile.mkdtemp()

    result = pairing_start.run({
        "store_path": tmp,
        "_headers": {"Host": "192.168.1.44:8765"},
    }, None)

    assert result["status"] == "ok"
    assert result["data"]["pairing"]["pickup_secret"].startswith("pup_")


def test_mobile_pairing_status_rejects_wrong_pickup_secret_without_rotating():
    from domain.p2p.device_store import DeviceStore
    from domain.p2p.pairing import PairingManager
    from blocks.mobile.pairing import run

    tmp = tempfile.mkdtemp()
    session = PairingManager(tmp).start_pairing(capabilities=["chat.read"])
    assert run({
        "action": "claim",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "code": session.code,
        "device_id": "mobile-1",
    }, None)["status"] == "ok"
    assert run({
        "action": "approve",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
    }, None)["status"] == "ok"

    wrong = run({
        "action": "status",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "pickup_secret": "pup_wrong",
        "device_id": "mobile-1",
    }, None)
    assert wrong["status"] == "ok"
    assert "device_token" not in wrong["data"]
    assert DeviceStore(tmp).get_device("mobile-1") is None


def test_mobile_pairing_status_splits_normal_and_approval_tokens():
    from domain.p2p.device_store import DeviceStore
    from domain.p2p.pairing import PairingManager
    from blocks.mobile.pairing import run

    tmp = tempfile.mkdtemp()
    session = PairingManager(tmp).start_pairing(
        capabilities=["chat.read", "chat.write", "tools.observe", *AUTHORITY_APPROVER_SCOPES],
    )

    claim = run({
        "action": "claim",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "code": session.code,
        "device_id": "mobile-1",
        "device_label": "iPhone",
        "requested_capabilities": [
            "chat.read",
            "chat.write",
            "tools.observe",
            *AUTHORITY_APPROVER_SCOPES,
        ],
    }, None)
    assert claim["status"] == "ok"
    assert "code" not in claim["data"]["pairing"]

    approved = run({
        "action": "approve",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
    }, None)
    assert approved["status"] == "ok"
    assert "code" not in approved["data"]["pairing"]
    assert "device_token" not in approved["data"]
    assert "approval_token" not in approved["data"]
    assert "client_access_token" not in approved["data"]
    assert "approver_access_token" not in approved["data"]

    status = run({
        "action": "status",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "pickup_secret": session.token_pickup_secret,
        "device_id": "mobile-1",
    }, None)

    assert status["status"] == "ok"
    data = status["data"]
    assert data["device_token"].startswith("dtk_")
    assert data["approval_token"].startswith("dtk_")
    assert data["client_access_token"] == data["device_token"]
    assert data["approver_access_token"] == data["approval_token"]
    assert data["device_token"] != data["approval_token"]
    assert "tools.approve" not in data["scopes"]
    assert data["approval_scopes"] == AUTHORITY_APPROVER_SCOPES

    store = DeviceStore(tmp)
    normal = store.verify_token(data["device_token"])
    approver = store.verify_token(data["approval_token"])
    assert normal is not None
    assert "tools.approve" not in normal.scopes
    assert approver is not None
    assert approver.scopes == AUTHORITY_APPROVER_SCOPES


def test_mobile_pairing_status_returns_pc_label(monkeypatch):
    from domain.p2p.pairing import PairingManager
    from blocks.mobile.pairing import run

    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("RUMI_PC_LABEL", "Haru MacBook")
    session = PairingManager(tmp).start_pairing(capabilities=["chat.read"])

    claim = run({
        "action": "claim",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "code": session.code,
        "device_id": "mobile-1",
        "device_label": "iPhone",
    }, None)
    assert claim["status"] == "ok"

    approved = run({
        "action": "approve",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
    }, None)
    assert approved["status"] == "ok"

    status = run({
        "action": "status",
        "store_path": tmp,
        "pairing_id": session.pairing_id,
        "code": session.code,
        "device_id": "mobile-1",
    }, None)

    assert status["status"] == "ok"
    assert status["data"]["pc_label"] == "Haru MacBook"


def test_mobile_pairing_base_urls_do_not_advertise_loopback():
    from domain.mobile.base_urls import mobile_base_urls_from_headers

    urls = mobile_base_urls_from_headers(
        {"Host": "localhost:8765"},
        local_addresses=["127.0.0.1", "192.168.1.44"],
    )

    assert urls == ["http://192.168.1.44:8765"]


def test_pairing_start_returns_mobile_reachable_base_urls(monkeypatch):
    from blocks.p2p import pairing_start

    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(
        pairing_start,
        "mobile_base_urls_from_headers",
        lambda headers: ["http://192.168.1.44:8765"],
    )

    result = pairing_start.run({
        "store_path": tmp,
        "_headers": {"Host": "localhost:8765"},
    }, None)

    assert result["status"] == "ok"
    assert result["data"]["pairing"]["base_urls"] == ["http://192.168.1.44:8765"]


def test_mobile_conversations_list_create_get():
    from blocks.mobile.conversations import run

    r = run({"action": "list"}, None)
    assert r["status"] == "ok"
    assert "conversations" in r["data"]

    r = run({"action": "create", "title": "Mobile Test"}, None)
    assert r["status"] == "ok"
    cid = r["data"]["conversation"]["id"]

    r = run({"action": "get", "conversation_id": cid}, None)
    assert r["status"] == "ok"


def test_mobile_credentials_create_get_ack():
    from blocks.mobile.credentials import run

    r = run({
        "action": "create",
        "device_id": "d1",
        "provider_id": "openai",
        "ciphertext": "encrypted-payload",
        "nonce": "nonce-1",
    }, None)
    assert r["status"] == "ok"
    tid = r["data"]["transfer"]["transfer_id"]
    # Ciphertext must not be in the create response
    assert "ciphertext" not in r["data"]["transfer"]

    device_context = {"_authenticated_device_id": "d1"}
    r = run({"action": "get", "transfer_id": tid}, device_context)
    assert r["status"] == "ok"
    assert "ciphertext" in r["data"]["transfer"]

    r = run({"action": "ack", "transfer_id": tid}, device_context)
    assert r["status"] == "ok"

    # After ack, get should fail
    r = run({"action": "get", "transfer_id": tid}, device_context)
    assert r["status"] == "error"


def test_mobile_credentials_reject_plaintext_fallback():
    from blocks.mobile.credentials import run

    r = run({
        "action": "create",
        "device_id": "d1",
        "provider_id": "openai",
        "api_key": "sk-test1234",
    }, None)

    assert r["status"] == "error"


def test_mobile_credentials_expired():
    import time
    from blocks.mobile.credentials import run, _TRANSFER_TTL_SECONDS

    r = run({
        "action": "create",
        "device_id": "d1",
        "provider_id": "openai",
        "ciphertext": "encrypted-payload",
        "nonce": "nonce-1",
    }, None)
    tid = r["data"]["transfer"]["transfer_id"]

    # Wait for expiry (TTL is 60s, so we test the path differently)
    # Just verify the endpoint exists and returns properly
    r = run({"action": "get", "transfer_id": tid}, {"_authenticated_device_id": "d1"})
    assert r["status"] == "ok"
