"""Direct regressions for the captured Pack v4 control plane."""

from __future__ import annotations

import json
import http.cookiejar
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from core_runtime.pack_control_v4 import (
    PACK_CONTROL_CONTRACT,
    PackControlDenied,
    PackControlUnavailable,
    PackControlUnapproved,
    capture_pack_control_session,
)
from core_runtime.authority.v4 import AuditUnavailable, AuthorityStore
from core_runtime.pack_api_server import PackAPIServer
from core_runtime.panel_auth import PanelAuthManager
from core_runtime.bootstrap.profile_capture import (
    capture_default_profile,
    prepare_default_profile_confirmation,
)
import core_runtime.pack_control_v4 as pack_control


TARGET_PACK = "rumi_git_read_pack"
REQUIRED_PACK = "rumi_file_inspect_pack"


@pytest.fixture
def captured_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Capture one isolated canonical Defaults Profile and approval store."""
    user_data = tmp_path / "user-data"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    capture_default_profile(confirmation=prepare_default_profile_confirmation())
    session = capture_pack_control_session()
    state_path = user_data / "workspaces" / "defaults" / "activation" / "active.json"
    yield session, state_path, user_data


def _invoke(
    session, operation: str, payload: dict | None = None, session_id: str = "session-a"
):
    return session.invoke(
        PACK_CONTROL_CONTRACT,
        operation,
        {**(payload or {}), "_session_id": session_id},
    )


def _approve_target(session) -> None:
    _invoke(session, "pack.install", {"pack_id": TARGET_PACK})
    candidate = _invoke(session, "approval.candidate", {"pack_id": TARGET_PACK})
    _invoke(
        session,
        "approval.approve",
        {"pack_id": TARGET_PACK, "candidate_id": candidate["candidate_id"]},
    )


def test_catalog_install_approve_enable_and_restart_read_back(captured_session) -> None:
    """The positive lifecycle survives a fresh captured session."""
    session, _state_path, user_data = captured_session
    initial = _invoke(session, "catalog.read")
    assert initial["count"] == 143
    target = next(item for item in initial["packs"] if item["pack_id"] == TARGET_PACK)
    assert target["installed"] is False
    assert target["enabled"] is False
    assert target["approved"] is False

    assert _invoke(session, "pack.install", {"pack_id": TARGET_PACK})["installed"]
    candidate = _invoke(
        session,
        "approval.candidate",
        {"pack_id": TARGET_PACK},
    )
    approved = _invoke(
        session,
        "approval.approve",
        {"pack_id": TARGET_PACK, "candidate_id": candidate["candidate_id"]},
    )
    assert approved["approved"] is True
    enabled = _invoke(session, "pack.enable", {"pack_id": TARGET_PACK})
    assert enabled["enabled"] is True

    restarted = capture_pack_control_session()
    status = _invoke(restarted, "pack.status", {"pack_id": TARGET_PACK})
    assert status["installed"] is True
    assert status["approved"] is True
    assert status["enabled"] is True

    first_activation = capture_default_profile().activation["activation_id"]
    assert (
        _invoke(restarted, "pack.disable", {"pack_id": TARGET_PACK})["enabled"] is False
    )
    recaptured = capture_pack_control_session()
    assert (
        _invoke(recaptured, "pack.status", {"pack_id": TARGET_PACK})["enabled"] is False
    )
    assert capture_default_profile().activation["activation_id"] != first_activation

    from core_runtime.authority.v4 import AuthorityStore

    with AuthorityStore(user_data / "authority" / "v4.sqlite3") as authority:
        assert authority.active_activation_reservation(str(first_activation)) is None


def test_enable_does_not_require_unrelated_pack_install_or_approval(
    captured_session,
) -> None:
    """Activation approval is limited to the requested Pack dependency closure."""

    session, _state_path, _user_data = captured_session
    unrelated = "defaults"
    assert _invoke(session, "pack.status", {"pack_id": unrelated})["installed"] is False
    _approve_target(session)
    assert _invoke(session, "pack.enable", {"pack_id": TARGET_PACK})["enabled"] is True
    restarted = capture_pack_control_session()
    assert (
        _invoke(restarted, "pack.status", {"pack_id": unrelated})["approved"] is False
    )


def test_required_pack_rejects_disable_and_revoke_before_side_effects(
    captured_session,
) -> None:
    """A bundled Profile Pack cannot be disabled or partially revoked."""

    session, _state_path, user_data = captured_session
    initial = _invoke(session, "pack.status", {"pack_id": REQUIRED_PACK})
    assert initial["required"] is True
    candidate = _invoke(
        session,
        "approval.candidate",
        {"pack_id": REQUIRED_PACK},
    )
    _invoke(
        session,
        "approval.approve",
        {"pack_id": REQUIRED_PACK, "candidate_id": candidate["candidate_id"]},
    )
    approval_path = (
        user_data / "pack_control" / "approvals" / "defaults" / f"{REQUIRED_PACK}.json"
    )
    approval_before = approval_path.read_bytes()
    activation_before = capture_default_profile().activation["activation_id"]

    with pytest.raises(PackControlDenied, match="required Pack cannot be disabled"):
        _invoke(session, "pack.disable", {"pack_id": REQUIRED_PACK})
    with pytest.raises(
        PackControlDenied, match="required Pack approval cannot be revoked"
    ):
        _invoke(session, "approval.revoke", {"pack_id": REQUIRED_PACK})

    assert approval_path.read_bytes() == approval_before
    assert capture_default_profile().activation["activation_id"] == activation_before
    status = _invoke(session, "pack.status", {"pack_id": REQUIRED_PACK})
    assert status["approved"] is True
    assert status["enabled"] is True


def test_approval_is_session_bound_one_shot_and_not_implicit(captured_session) -> None:
    """Forged/replayed approval and automatic enablement fail closed."""
    session, _state_path, _user_data = captured_session
    _invoke(session, "pack.install", {"pack_id": TARGET_PACK})
    candidate = _invoke(session, "approval.candidate", {"pack_id": TARGET_PACK})
    with pytest.raises(PackControlDenied, match="binding"):
        _invoke(
            session,
            "approval.approve",
            {"pack_id": TARGET_PACK, "candidate_id": candidate["candidate_id"]},
            session_id="forged-session",
        )
    status = _invoke(session, "pack.status", {"pack_id": TARGET_PACK})
    assert status["approved"] is False
    assert status["enabled"] is False
    with pytest.raises(PackControlDenied, match="missing|used"):
        _invoke(
            session,
            "approval.approve",
            {"pack_id": TARGET_PACK, "candidate_id": candidate["candidate_id"]},
        )
    with pytest.raises(PackControlDenied, match="not trusted"):
        _invoke(
            session,
            "pack.enable",
            {"pack_id": TARGET_PACK, "approved": True},
        )


def test_never_approved_revoke_is_unapproved_not_unavailable(captured_session) -> None:
    """A normal missing approval leaf is authoritative absence, not an outage."""

    session, _state_path, _user_data = captured_session
    _invoke(session, "pack.install", {"pack_id": TARGET_PACK})

    with pytest.raises(PackControlUnapproved, match="approval_required"):
        _invoke(session, "approval.revoke", {"pack_id": TARGET_PACK})


def test_corrupt_approval_revoke_remains_unavailable(captured_session) -> None:
    """Unreadable approval state must not be normalized into unapproved."""

    session, _state_path, user_data = captured_session
    _approve_target(session)
    approval_path = (
        user_data / "pack_control" / "approvals" / "defaults" / f"{TARGET_PACK}.json"
    )
    approval_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(PackControlUnavailable, match="approval_unreadable"):
        _invoke(session, "approval.revoke", {"pack_id": TARGET_PACK})


def test_revoke_persists_audit_and_rejects_revision_replay_after_restart(
    captured_session,
) -> None:
    """Disable and explicit revoke are distinct, durable ceremonies."""

    session, _state_path, user_data = captured_session
    _approve_target(session)
    assert _invoke(session, "pack.enable", {"pack_id": TARGET_PACK})["enabled"]

    restarted = capture_pack_control_session()
    assert _invoke(restarted, "pack.status", {"pack_id": TARGET_PACK})["enabled"]
    assert not _invoke(restarted, "pack.disable", {"pack_id": TARGET_PACK})["enabled"]
    approval_path = (
        user_data / "pack_control" / "approvals" / "defaults" / f"{TARGET_PACK}.json"
    )
    approved_payload = approval_path.read_bytes()
    revoked = _invoke(restarted, "approval.revoke", {"pack_id": TARGET_PACK})
    assert revoked["approved"] is False
    assert revoked["enabled"] is False
    assert revoked["approval_status"] == "revoked"

    after_restart = capture_pack_control_session()
    status = _invoke(after_restart, "pack.status", {"pack_id": TARGET_PACK})
    assert status["approved"] is False
    assert status["enabled"] is False
    assert status["approval_reason"] == "approval_revoked"
    with pytest.raises(PackControlDenied, match="approval_revoked"):
        _invoke(after_restart, "approval.revoke", {"pack_id": TARGET_PACK})

    approval_path.write_bytes(approved_payload)
    replayed = capture_pack_control_session()
    assert (
        _invoke(replayed, "pack.status", {"pack_id": TARGET_PACK})["approval_reason"]
        == "approval_revoked"
    )
    with pytest.raises(PackControlDenied, match="approval_revoked"):
        _invoke(replayed, "pack.enable", {"pack_id": TARGET_PACK})

    replacement = _invoke(
        replayed,
        "approval.candidate",
        {"pack_id": TARGET_PACK},
    )
    _invoke(
        replayed,
        "approval.approve",
        {
            "pack_id": TARGET_PACK,
            "candidate_id": replacement["candidate_id"],
        },
    )
    replacement_payload = json.loads(approval_path.read_text(encoding="utf-8"))
    assert replacement_payload["approval_revision"] != revoked["approval_revision"]
    assert _invoke(replayed, "pack.status", {"pack_id": TARGET_PACK})["approved"]

    with AuthorityStore(user_data / "authority" / "v4.sqlite3") as authority:
        event = next(
            item
            for item in reversed(authority.audit_events())
            if item["event_type"] == "pack_approval_revoked"
        )
    assert event["event_state"] == "committed"
    assert event["payload"]["pack_id"] == TARGET_PACK
    assert event["payload"]["approval_revision"] == revoked["approval_revision"]


def test_revoke_audit_failure_rolls_back_and_leaves_approval_usable(
    captured_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unavailable authoritative audit leaves no partial revocation."""

    session, _state_path, user_data = captured_session
    _approve_target(session)
    assert _invoke(session, "pack.enable", {"pack_id": TARGET_PACK})["enabled"]
    approval_path = (
        user_data / "pack_control" / "approvals" / "defaults" / f"{TARGET_PACK}.json"
    )
    approval_before = approval_path.read_bytes()
    original_append = AuthorityStore._append_audit

    def fail_revoke_audit(self, connection, **kwargs):
        if kwargs.get("event_type") == "pack_approval_revoked":
            raise AuditUnavailable("injected audit failure")
        return original_append(self, connection, **kwargs)

    monkeypatch.setattr(AuthorityStore, "_append_audit", fail_revoke_audit)
    with pytest.raises(PackControlDenied, match="not committed"):
        _invoke(session, "approval.revoke", {"pack_id": TARGET_PACK})
    assert approval_path.read_bytes() == approval_before
    with AuthorityStore(user_data / "authority" / "v4.sqlite3") as authority:
        assert not authority.is_revoked(
            "approval",
            json.loads(approval_before)["approval_revision"],
        )
    status = _invoke(session, "pack.status", {"pack_id": TARGET_PACK})
    assert status["approved"] is True
    assert status["enabled"] is True


@pytest.mark.parametrize("pack_id", ["unknown-pack", "../defaultspack", "a/b"])
def test_unknown_and_traversal_pack_ids_fail_closed(
    captured_session, pack_id: str
) -> None:
    """Only an exact canonical catalog identity may cross the boundary."""
    session, _state_path, _user_data = captured_session
    with pytest.raises(PackControlDenied, match="canonical"):
        _invoke(session, "pack.install", {"pack_id": pack_id})


def test_cross_workspace_stale_profile_and_tampered_install_fail_closed(
    captured_session,
) -> None:
    """Workspace, Profile revision, and installed artifact binding are exact."""
    session, state_path, user_data = captured_session
    with pytest.raises(PackControlDenied, match="workspace_id"):
        _invoke(
            session,
            "catalog.read",
            {"workspace_id": "workspace-b"},
        )
    _invoke(session, "pack.install", {"pack_id": TARGET_PACK})
    control_path = user_data / "pack_control" / "defaults.v4.json"
    control = json.loads(control_path.read_text(encoding="utf-8"))
    artifact_digest = control["installed"][TARGET_PACK]["artifact_digest"]
    control["installed"][TARGET_PACK]["artifact_digest"] = "sha256:" + "0" * 64
    control_path.write_text(json.dumps(control), encoding="utf-8")
    with pytest.raises(PackControlDenied, match="tampered"):
        _invoke(session, "pack.status", {"pack_id": TARGET_PACK})
    control["installed"][TARGET_PACK]["artifact_digest"] = artifact_digest
    control_path.write_text(json.dumps(control), encoding="utf-8")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["envelope_digest"] = "sha256:" + "0" * 64
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(PackControlDenied, match="missing|invalid"):
        _invoke(session, "catalog.read")
    with pytest.raises(PackControlDenied, match="missing|invalid"):
        _invoke(session, "profile.reload")


def test_tampered_approval_and_symlinked_pack_fail_closed(
    captured_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approval signatures and Pack filesystem boundaries are authoritative."""
    session, _state_path, user_data = captured_session
    _approve_target(session)
    approval_path = (
        user_data / "pack_control" / "approvals" / "defaults" / f"{TARGET_PACK}.json"
    )
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["workspace_id"] = "forged-workspace"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(PackControlDenied, match="signature"):
        _invoke(session, "pack.enable", {"pack_id": TARGET_PACK})

    actual = tmp_path / "actual-pack"
    actual.mkdir()
    (actual / "artifact.txt").write_text("artifact", encoding="utf-8")
    redirected = tmp_path / "redirected-pack"
    redirected.symlink_to(actual, target_is_directory=True)
    monkeypatch.setattr(
        pack_control,
        "resolve_pack_root",
        lambda _pack_id: redirected,
    )
    with pytest.raises(PackControlDenied, match="symlinked"):
        _invoke(session, "pack.install", {"pack_id": TARGET_PACK})


def test_missing_profile_and_symlinked_state_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No session is reconstructed from missing or redirected Profile state."""
    user_data = tmp_path / "missing"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    capture_default_profile(confirmation=prepare_default_profile_confirmation())
    capture_pack_control_session()
    pointer = user_data / "workspaces" / "defaults" / "activation" / "active.json"
    pointer.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    pointer.symlink_to(outside)
    with pytest.raises(PackControlDenied, match="missing"):
        capture_pack_control_session()


def test_profile_identity_traversal_fails_before_control_state_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Profile persistence cannot escape the Authority-owned control root."""
    user_data = tmp_path / "user-data"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    capture_default_profile(confirmation=prepare_default_profile_confirmation())
    session = capture_pack_control_session()
    with pytest.raises(PackControlDenied, match="profile_id"):
        _invoke(session, "catalog.read", {"profile_id": "../escaped"})


def test_generic_dispatch_is_retired_without_client_selected_execution(
    captured_session,
) -> None:
    """The generic endpoint never trusts client-selected Broker identities."""
    session, state_path, _user_data = captured_session
    auth = PanelAuthManager(bootstrap_secret="desktop-bootstrap")
    server = PackAPIServer(
        host="127.0.0.1",
        port=0,
        panel_auth_manager=auth,
        dispatch_session=session,
    )
    server.start()
    assert server.server is not None
    port = int(server.server.server_address[1])
    origin = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    def post(path: str, body: dict, headers: dict | None = None) -> dict:
        request = urllib.request.Request(
            origin + path,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                **(headers or {}),
            },
            method="POST",
        )
        with opener.open(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def assert_post_denied(
        path: str,
        body: dict,
        expected_status: int,
        headers: dict | None = None,
    ) -> None:
        with pytest.raises(urllib.error.HTTPError) as denied:
            post(path, body, headers)
        assert denied.value.code == expected_status
        payload = json.loads(denied.value.read().decode("utf-8"))
        assert payload["data"] == {
            "api_version": "io.tobkiri.pack-api.v4",
            "retired_route": "/api/v4/dispatch",
            "state": "legacy_api_retired",
            "write_set": [],
        }

    try:
        dispatch_body = {
            "contract_id": PACK_CONTROL_CONTRACT,
            "operation_id": "catalog.read",
            "payload": {},
        }
        before = state_path.read_bytes()
        assert_post_denied("/api/v4/dispatch", dispatch_body, 410)
        assert_post_denied(
            "/api/v4/dispatch",
            dispatch_body,
            410,
            {"Authorization": "Bearer formerly-valid-internal-token"},
        )
        bootstrap = post(
            "/api/panel/auth/bootstrap",
            {},
            {"X-Rumi-Desktop-Bootstrap": "desktop-bootstrap"},
        )
        exchange = post(
            "/api/panel/auth/exchange",
            {"code": bootstrap["data"]["code"]},
        )
        csrf = exchange["data"]["csrf_token"]
        assert_post_denied(
            "/api/v4/dispatch",
            {
                "contract_id": "attacker.selected.contract",
                "operation_id": "attacker.selected.operation",
                "payload": {"pack_id": TARGET_PACK},
            },
            410,
            {"X-Rumi-CSRF": csrf},
        )
        assert state_path.read_bytes() == before
    finally:
        server.stop()


def test_pack_control_state_hardlink_fails_closed(captured_session) -> None:
    session, _state_path, user_data = captured_session
    state = user_data / "pack_control" / "defaults.v4.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    outside = user_data / "outside-state"
    outside.write_text(
        '{"version":"io.tobkiri.pack-control-state.v4","profile_id":"defaults","installed":{}}\n',
        encoding="utf-8",
    )
    os.link(outside, state)

    with pytest.raises(PackControlDenied, match="state is unreadable"):
        _invoke(session, "catalog.read")


def test_pack_approval_hardlink_fails_closed(captured_session) -> None:
    session, _state_path, user_data = captured_session
    _approve_target(session)
    approval = (
        user_data / "pack_control" / "approvals" / "defaults" / f"{TARGET_PACK}.json"
    )
    outside = user_data / "outside-approval"
    shutil.copyfile(approval, outside)
    approval.unlink()
    os.link(outside, approval)

    status = _invoke(session, "pack.status", {"pack_id": TARGET_PACK})
    assert status["approved"] is False
    assert status["approval_reason"] == "approval_unreadable"


def test_pack_control_root_replacement_fails_closed(captured_session) -> None:
    session, _state_path, user_data = captured_session
    _invoke(session, "catalog.read")
    root = user_data / "pack_control"
    displaced = user_data / "pack-control-displaced"
    root.rename(displaced)
    root.mkdir()

    with pytest.raises(PackControlDenied, match="state is unreadable"):
        _invoke(session, "catalog.read")


def test_pack_approval_root_replacement_fails_closed(captured_session) -> None:
    session, _state_path, user_data = captured_session
    _approve_target(session)
    root = user_data / "pack_control" / "approvals" / "defaults"
    displaced = user_data / "approval-displaced"
    root.rename(displaced)
    root.mkdir()

    status = _invoke(session, "pack.status", {"pack_id": TARGET_PACK})
    assert status["approved"] is False
    assert status["approval_reason"] == "approval_unreadable"
