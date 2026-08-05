"""Direct regressions for the captured Pack v4 control plane."""

from __future__ import annotations

import json
import http.cookiejar
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from core_runtime.pack_control_v4 import (
    PACK_CONTROL_CONTRACT,
    PackControlDenied,
    capture_pack_control_session,
)
from core_runtime.pack_api_server import PackAPIServer
from core_runtime.panel_auth import PanelAuthManager
from core_runtime.bootstrap.profile_capture import (
    capture_default_profile,
    prepare_default_profile_confirmation,
)
import core_runtime.pack_control_v4 as pack_control


TARGET_PACK = "rumi_git_read_pack"


@pytest.fixture
def captured_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Capture one isolated canonical Defaults Profile and approval store."""
    user_data = tmp_path / "user-data"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    capture_default_profile(confirmation=prepare_default_profile_confirmation())
    session = capture_pack_control_session()
    state_path = user_data / "profiles" / "defaults" / "v4" / "active.json"
    yield session, state_path, user_data


def _invoke(session, operation: str, payload: dict | None = None, session_id: str = "session-a"):
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
    session, _state_path, _user_data = captured_session
    initial = _invoke(session, "catalog.read")
    assert initial["count"] == 142
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
    with pytest.raises(PackControlDenied, match="immutable"):
        _invoke(session, "pack.enable", {"pack_id": TARGET_PACK})

    restarted = capture_pack_control_session()
    status = _invoke(restarted, "pack.status", {"pack_id": TARGET_PACK})
    assert status["installed"] is True
    assert status["approved"] is True
    assert status["enabled"] is False


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


@pytest.mark.parametrize("pack_id", ["unknown-pack", "../defaultspack", "a/b"])
def test_unknown_and_traversal_pack_ids_fail_closed(captured_session, pack_id: str) -> None:
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
    approval_path = user_data / "pack_control" / "approvals" / "defaults" / f"{TARGET_PACK}.json"
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
    pointer = user_data / "profiles" / "defaults" / "v4" / "active.json"
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


def test_real_http_local_auth_dispatch_lifecycle_has_zero_legacy_calls(
    captured_session,
) -> None:
    """Production-shaped HTTP auth/CSRF transport never calls a legacy route."""
    session, _state_path, _user_data = captured_session
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
    paths: list[str] = []

    def post(path: str, body: dict, headers: dict | None = None) -> dict:
        paths.append(path)
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

    try:
        dispatch_body = {
            "contract_id": PACK_CONTROL_CONTRACT,
            "operation_id": "catalog.read",
            "payload": {},
        }
        assert_post_denied("/api/v4/dispatch", dispatch_body, 401)
        assert_post_denied(
            "/api/v4/dispatch",
            dispatch_body,
            401,
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
        assert_post_denied("/api/v4/dispatch", dispatch_body, 401)

        def dispatch(operation_id: str, payload: dict | None = None) -> dict:
            envelope = post(
                "/api/v4/dispatch",
                {
                    "contract_id": PACK_CONTROL_CONTRACT,
                    "operation_id": operation_id,
                    "payload": payload or {},
                },
                {"X-Rumi-CSRF": csrf},
            )
            assert envelope["success"] is True
            return envelope["data"]

        assert dispatch("catalog.read")["count"] == 142
        dispatch("pack.install", {"pack_id": TARGET_PACK})
        candidate = dispatch("approval.candidate", {"pack_id": TARGET_PACK})
        dispatch(
            "approval.approve",
            {
                "pack_id": TARGET_PACK,
                "candidate_id": candidate["candidate_id"],
            },
        )
        with pytest.raises(urllib.error.HTTPError) as conflict:
            dispatch("pack.enable", {"pack_id": TARGET_PACK})
        assert conflict.value.code == 409
        assert dispatch("runtime.restart")["restart_requested"] is True
        restarted_status = dispatch(
            "pack.status",
            {"pack_id": TARGET_PACK},
        )
        assert restarted_status["enabled"] is False
        assert restarted_status["approved"] is True
        assert all(path != "/api/panel/packs" for path in paths)
        assert not any(path.startswith("/api/panel/packs/") for path in paths)
    finally:
        from core_runtime.restart_control import (
            clear_kernel_restart_request,
        )

        clear_kernel_restart_request()
        server.stop()
