"""Strict regression coverage for the native file-inspect GUI launch path."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import secrets
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator

import pytest

from core_runtime.capability_binding_registration import (
    register_pack_binding_handlers,
)
from core_runtime.global_contract_dispatch import (
    GlobalContractUnavailable,
    invoke_global_contract,
    selected_global_providers,
)
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.resolved_profile import (
    ResolvedProfile,
    resolution_input_from_startup_profile,
    resolve_profile,
)
from core_runtime.resolved_profile_scope import (
    activate_resolved_profile,
    restore_resolved_profile,
)
from core_runtime.startup_profiles import StartupProfileManager
from ecosystem.rumi_workspace_mount_pack.runtime.mounts import WorkspaceMountStore


ECOSYSTEM = Path(__file__).resolve().parents[1] / "ecosystem"
RUNTIME_ROOT = Path(__file__).resolve().parents[1]
HTTP_RUNNER = Path(__file__).resolve().parent / "fixtures" / "native_qa_http_server.py"

PROFILE_ID = "qa-file-inspect"
FILE_INSPECT_PACK = "rumi_file_inspect_pack"
CONVERSATION_PACK = "rumi_conversation_store_pack"
WORKSPACE_PACK = "rumi_workspace_mount_pack"
FILE_INSPECT_CONTRACT = "rumi.service.file.inspect.v1"
CONVERSATION_CONTRACT = "rumi.resource.conversation.v1"

_PROFILE_CAPABILITIES = [
    "conversation.read",
    "conversation.manage",
    "message.read",
    "message.manage",
    "conversation.migrate",
    "file.inspect",
    "workspace.metadata.read",
    "workspace.mount.manage",
    "host.authority.consume",
]


class _Approval:
    """Host-owned approval fixture with explicit deny modes."""

    def __init__(
        self,
        *,
        unapproved: set[str] | None = None,
        blocked: set[str] | None = None,
    ) -> None:
        self.unapproved = set(unapproved or ())
        self.blocked = set(blocked or ())

    def get_approval(self, pack_id: str) -> object | None:
        """Return a fixture grant only for a pack that passes host policy."""
        return object() if self.is_pack_approved_and_verified(pack_id)[0] else None

    def is_pack_approved_and_verified(self, pack_id: str) -> tuple[bool, str]:
        """Return the explicit host decision for one pack."""
        if pack_id in self.blocked:
            return False, "blocked"
        if pack_id in self.unapproved:
            return False, "not_approved"
        return True, "verified fixture"

    def get_verified_pack_trust(
        self,
        pack_ids: tuple[str, ...],
    ) -> dict[str, str]:
        """Return verified trust only for packs approved by this fixture."""
        return {
            pack_id: "verified"
            for pack_id in pack_ids
            if self.is_pack_approved_and_verified(pack_id)[0]
        }


def _make_gui_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_conversation_pack: bool = False,
    launch: bool = False,
) -> tuple[StartupProfileManager, dict[str, Any], _Approval, Path]:
    """Create the persisted profile state produced by the control panel."""
    user_data = tmp_path / "user_data"
    storage_path = user_data / "settings" / "startup_profiles.json"
    approval = _Approval()
    manager = StartupProfileManager(
        storage_path=storage_path,
        ecosystem_dir=str(ECOSYSTEM),
        approval_manager=approval,
        seed_default_profile=False,
    )
    created = manager.create_profile(
        {
            "profile_id": PROFILE_ID,
            "name": "File Inspect QA",
            "base_pack": "defaultspack",
            "graph_id": "defaultspack.startup",
            "default_graph": "defaultspack.startup",
            "capability_profile_id": "defaultspack.startup",
            "launch_capability_graph": True,
            "policy": {"capabilities": list(_PROFILE_CAPABILITIES)},
        }
    )
    assert created.get("created") is True, created

    added = manager.add_pack_to_profile(PROFILE_ID, FILE_INSPECT_PACK)
    assert added.get("pack_added") == FILE_INSPECT_PACK, added
    if include_conversation_pack:
        added_conversation = manager.add_pack_to_profile(
            PROFILE_ID,
            CONVERSATION_PACK,
        )
        assert added_conversation.get("pack_added") == CONVERSATION_PACK

    activated = manager.activate_profile(PROFILE_ID)
    assert activated.get("activated") is True, activated

    if launch:
        # Keep the handoff local to the test while exercising the actual
        # StartupProfileManager persistence and launch-state transitions.
        monkeypatch.setattr(
            manager,
            "_compile_launch_capability_graph",
            lambda _profile: {
                "ok": True,
                "runtime_profile_key": None,
                "diagnostics": [],
            },
        )
        monkeypatch.setattr(
            manager,
            "_apply_profile_to_active_ecosystem",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            manager,
            "_record_capability_graph_result",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            manager,
            "_request_launch_handoff",
            lambda _profile: {"restart_requested": True},
        )
        launched = manager.launch_profile(PROFILE_ID)
        assert launched.get("launched") is True, launched

    state = manager.list_profiles_payload()
    profile = next(
        item for item in state["profiles"] if item["profile_id"] == PROFILE_ID
    )
    return manager, profile, approval, user_data


def _resolve_gui_profile(
    profile: dict[str, Any],
    approval: _Approval,
    *,
    healthy_pack_ids: set[str] | None = None,
) -> ResolvedProfile:
    """Resolve persisted GUI state through the same two-pass host flow."""
    provisional_input = resolution_input_from_startup_profile(profile)
    provisional = resolve_profile(
        provisional_input,
        ecosystem_dir=ECOSYSTEM,
    )
    verified_trust = approval.get_verified_pack_trust(
        provisional.selected_pack_ids
    )
    final_input = resolution_input_from_startup_profile(
        profile,
        verified_pack_trust=verified_trust,
    )
    final_input = replace(
        final_input,
        authorized_pack_ids=tuple(verified_trust),
        healthy_pack_ids=(
            tuple(sorted(healthy_pack_ids))
            if healthy_pack_ids is not None
            else ()
        ),
    )
    return resolve_profile(final_input, ecosystem_dir=ECOSYSTEM)


def _register(plan: ResolvedProfile, approval: _Approval) -> InterfaceRegistry:
    """Register only the providers in one resolved plan."""
    registry = InterfaceRegistry()
    result = register_pack_binding_handlers(
        interface_registry=registry,
        approval_manager=approval,
        ecosystem_dir=str(ECOSYSTEM),
        effective_pack_ids=plan.effective_pack_set,
    )
    assert result.ok is True, result.to_dict()
    return registry


@contextmanager
def _active(plan: ResolvedProfile) -> Iterator[None]:
    """Bind one immutable plan for the duration of a direct runtime call."""
    token = activate_resolved_profile(plan)
    try:
        yield
    finally:
        restore_resolved_profile(token)


def _workspace_binding(
    workspace: Path,
    mount: dict[str, Any],
) -> dict[str, Any]:
    """Build the Host-authenticated binding expected by file-inspect."""
    root = workspace.resolve()
    root_stat = root.stat()
    binding = {
        "workspace_id": "qa-workspace",
        "access": "read_only",
        "mount_revision": str(mount["updated_at"]),
        "canonical_root": str(root),
        "root_st_dev": int(root_stat.st_dev),
        "root_st_ino": int(root_stat.st_ino),
    }
    binding["root_identity"] = hashlib.sha256(
        json.dumps(
            binding,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return binding


def _read_workspace_file(
    plan: ResolvedProfile,
    registry: InterfaceRegistry,
    user_data: Path,
    workspace: Path,
) -> dict[str, Any]:
    """Read a real file through the activated file-inspect contract."""
    import ecosystem.rumi_workspace_mount_pack.runtime.mounts as mounts

    previous_user_data = mounts.USER_DATA_DIR
    mounts.USER_DATA_DIR = user_data
    try:
        store = WorkspaceMountStore(PROFILE_ID)
        snapshot = store.snapshot()
        if store.get("qa-workspace") is None:
            mounted = store.mount(
                "qa-workspace",
                str(workspace),
                expected_revision=int(snapshot["revision"]),
            )
            store.select(
                "qa-workspace",
                expected_revision=int(mounted["revision"]),
            )
        mount = store.get("qa-workspace")
        assert mount is not None
        binding = _workspace_binding(workspace, mount)
        with _active(plan):
            return invoke_global_contract(
                registry,
                FILE_INSPECT_CONTRACT,
                "read",
                {
                    "profile_id": PROFILE_ID,
                    "workspace_id": "qa-workspace",
                    "path": "hello.txt",
                    "require_selected": True,
                    "_workspace_binding": binding,
                },
            )
    finally:
        mounts.USER_DATA_DIR = previous_user_data


def _http_json(
    port: int,
    method: str,
    path: str,
    *,
    token: str | None = None,
    origin: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any, str]:
    """Make one dynamic-port request and return status, decoded body, raw text."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Connection": "close"}
    if origin:
        headers["Origin"] = origin
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read().decode("utf-8", errors="replace")
        try:
            decoded: Any = json.loads(raw)
        except json.JSONDecodeError:
            decoded = raw
        return response.status, decoded, raw
    finally:
        connection.close()


def _start_native_server(
    user_data: Path,
    tmp_path: Path,
    token: str,
) -> tuple[subprocess.Popen[str], dict[str, Any]]:
    """Start the real Defaults HTTP server in a fresh runtime subprocess."""
    ready_file = tmp_path / f"native-qa-ready-{time.monotonic_ns()}.json"
    environment = os.environ.copy()
    environment.update(
        {
            "RUMI_USER_DATA": str(user_data),
            "RUMI_QA_READY_FILE": str(ready_file),
            "RUMI_DEFAULTSPACK_LOCAL_TOKEN": token,
            "RUMI_ALLOW_HOST_EXECUTION": "true",
            "RUMI_DEFAULTSPACK_OPEN_BROWSER": "0",
            "DEFAULTS_HTTP_HOST": "127.0.0.1",
            "DEFAULTS_HTTP_PORT": "0",
            "PYTHONUNBUFFERED": "1",
        }
    )
    process = subprocess.Popen(
        [sys.executable, str(HTTP_RUNNER)],
        cwd=str(RUNTIME_ROOT),
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if ready_file.is_file():
            try:
                return process, json.loads(ready_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise AssertionError(
                "native QA HTTP subprocess exited before readiness: " + stderr
            )
        time.sleep(0.02)
    process.terminate()
    stdout, stderr = process.communicate(timeout=5)
    raise AssertionError(
        "native QA HTTP subprocess did not become ready: "
        + stderr
        + stdout
    )


def _stop_native_server(process: subprocess.Popen[str]) -> None:
    """Stop the test subprocess through its controlled stdin protocol."""
    stdout, stderr = process.communicate("STOP\n", timeout=15)
    assert process.returncode == 0, stderr + stdout


def test_gui_profile_launch_has_exactly_one_foundational_conversation_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The GUI file-inspect selection must retain the foundational provider."""
    manager, profile, approval, _user_data = _make_gui_profile(
        tmp_path,
        monkeypatch,
        launch=True,
    )
    state = manager.list_profiles_payload()
    assert state["active_profile_id"] == PROFILE_ID
    assert state["last_launched_profile_id"] == PROFILE_ID
    assert profile["packs"] == ["defaultspack", FILE_INSPECT_PACK]

    reloaded = StartupProfileManager(
        storage_path=manager.storage_path,
        ecosystem_dir=str(ECOSYSTEM),
        approval_manager=approval,
        seed_default_profile=False,
    ).list_profiles_payload()
    reloaded_profile = next(
        item for item in reloaded["profiles"] if item["profile_id"] == PROFILE_ID
    )
    assert reloaded["active_profile_id"] == PROFILE_ID
    assert reloaded["last_launched_profile_id"] == PROFILE_ID
    assert reloaded_profile["packs"] == ["defaultspack", FILE_INSPECT_PACK]

    first_plan = _resolve_gui_profile(reloaded_profile, approval)
    second_plan = _resolve_gui_profile(reloaded_profile, approval)
    conversation_providers = [
        provider
        for provider in first_plan.providers
        if provider.contract_id == CONVERSATION_CONTRACT
    ]
    assert len(conversation_providers) == 1
    assert conversation_providers[0].source_pack_id == CONVERSATION_PACK
    assert CONVERSATION_PACK in first_plan.effective_pack_set
    assert first_plan.effective_pack_set == second_plan.effective_pack_set
    assert first_plan.selected_pack_ids == second_plan.selected_pack_ids
    assert first_plan.plan_hash == second_plan.plan_hash


def test_defaults_profile_retains_foundational_provider_and_deterministic_closure(
    tmp_path: Path,
) -> None:
    """The auto-seeded Defaults Profile must not lose conversation ownership."""
    user_data = tmp_path / "user_data"
    manager = StartupProfileManager(
        storage_path=user_data / "settings" / "startup_profiles.json",
        ecosystem_dir=str(ECOSYSTEM),
        approval_manager=_Approval(),
        seed_default_profile=True,
    )
    payload = manager.list_profiles_payload()
    default_profile = next(
        item for item in payload["profiles"] if item["profile_id"] == "default-profile"
    )
    first_plan = _resolve_gui_profile(default_profile, _Approval())
    second_plan = _resolve_gui_profile(default_profile, _Approval())
    conversation_providers = [
        provider
        for provider in first_plan.providers
        if provider.contract_id == CONVERSATION_CONTRACT
    ]

    assert len(conversation_providers) == 1
    assert CONVERSATION_PACK in first_plan.effective_pack_set
    assert first_plan.effective_pack_set == second_plan.effective_pack_set
    assert first_plan.plan_hash == second_plan.plan_hash
    assert first_plan.effective_pack_set == tuple(
        sorted(first_plan.effective_pack_set)
    )


def test_authenticated_chat_and_file_read_survive_reload_and_runtime_restart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Exercise real HTTP and filesystem operations across two fresh runtimes."""
    monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
    manager, profile, approval, user_data = _make_gui_profile(
        tmp_path,
        monkeypatch,
        launch=True,
    )
    plan = _resolve_gui_profile(profile, approval)
    registry = _register(plan, approval)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text(
        "native GUI regression file\n",
        encoding="utf-8",
    )
    first_read = _read_workspace_file(plan, registry, user_data, workspace)
    assert first_read["content"] == "native GUI regression file\n"
    assert first_read["read_only"] is True

    token = secrets.token_urlsafe(32)
    process, ready = _start_native_server(user_data, tmp_path, token)
    try:
        port = int(ready["port"])
        origin = f"http://127.0.0.1:{port}"
        health_status, health_body, health_raw = _http_json(
            port,
            "GET",
            "/api/health",
        )
        assert health_status == 200, health_raw
        assert health_body["status"] == "ok"

        shell_status, _shell_body, shell_raw = _http_json(
            port,
            "GET",
            "/chat",
            token=token,
            origin=origin,
        )
        assert shell_status == 200, shell_raw

        unauth_status, unauth_body, unauth_raw = _http_json(
            port,
            "GET",
            "/api/integrations/secrets",
            origin=origin,
        )
        assert unauth_status == 401, (unauth_raw, unauth_body)

        chat_status, chat_body, chat_raw = _http_json(
            port,
            "POST",
            "/api/chat/conversations",
            token=token,
            origin=origin,
            payload={"metadata": {"title": "Native QA"}},
        )
        assert chat_status == 200, chat_raw
        assert chat_body["status"] == "ok"
        assert int(ready["conversation_provider_count"]) == 1
    finally:
        _stop_native_server(process)

    reloaded_payload = StartupProfileManager(
        storage_path=manager.storage_path,
        ecosystem_dir=str(ECOSYSTEM),
        approval_manager=approval,
        seed_default_profile=False,
    ).list_profiles_payload()
    reloaded_profile = next(
        item
        for item in reloaded_payload["profiles"]
        if item["profile_id"] == PROFILE_ID
    )
    assert reloaded_payload["active_profile_id"] == PROFILE_ID
    assert reloaded_payload["last_launched_profile_id"] == PROFILE_ID
    assert reloaded_profile["packs"] == ["defaultspack", FILE_INSPECT_PACK]

    reloaded_plan = _resolve_gui_profile(reloaded_profile, approval)
    assert reloaded_plan.plan_hash == plan.plan_hash
    reloaded_registry = _register(reloaded_plan, approval)
    second_read = _read_workspace_file(
        reloaded_plan,
        reloaded_registry,
        user_data,
        workspace,
    )
    assert second_read["content"] == "native GUI regression file\n"

    second_process, second_ready = _start_native_server(
        user_data,
        tmp_path,
        token,
    )
    try:
        second_port = int(second_ready["port"])
        second_origin = f"http://127.0.0.1:{second_port}"
        chat_status, chat_body, chat_raw = _http_json(
            second_port,
            "POST",
            "/api/chat/conversations",
            token=token,
            origin=second_origin,
            payload={"metadata": {"title": "Native QA after restart"}},
        )
        assert chat_status == 200, chat_raw
        assert chat_body["status"] == "ok"
        assert int(second_ready["conversation_provider_count"]) == 1
    finally:
        _stop_native_server(second_process)


def test_file_inspect_rejects_traversal_cross_workspace_and_secret_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Keep file inspection jailed to the selected read-only workspace."""
    monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
    _manager, profile, approval, user_data = _make_gui_profile(
        tmp_path,
        monkeypatch,
    )
    plan = _resolve_gui_profile(profile, approval)
    registry = _register(plan, approval)

    import ecosystem.rumi_workspace_mount_pack.runtime.mounts as mounts

    monkeypatch.setattr(mounts, "USER_DATA_DIR", user_data)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("safe\n", encoding="utf-8")
    (workspace / ".env").write_text("SECRET=must-not-read\n", encoding="utf-8")
    other_workspace = tmp_path / "other-workspace"
    other_workspace.mkdir()
    (other_workspace / "other.txt").write_text("other\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")

    store = WorkspaceMountStore(PROFILE_ID)
    first_mount = store.mount(
        "qa-workspace",
        str(workspace),
        expected_revision=0,
    )
    second_mount = store.mount(
        "other-workspace",
        str(other_workspace),
        expected_revision=int(first_mount["revision"]),
    )
    store.select(
        "qa-workspace",
        expected_revision=int(second_mount["revision"]),
    )
    binding = _workspace_binding(workspace, store.get("qa-workspace") or {})

    def read(path: str, *, workspace_id: str = "qa-workspace") -> Any:
        payload = {
            "profile_id": PROFILE_ID,
            "workspace_id": workspace_id,
            "path": path,
            "require_selected": True,
            "_workspace_binding": binding,
        }
        with _active(plan):
            return invoke_global_contract(
                registry,
                FILE_INSPECT_CONTRACT,
                "read",
                payload,
            )

    with pytest.raises(PermissionError, match="escapes the workspace mount"):
        read("../outside.txt")
    with pytest.raises(PermissionError, match="absolute paths"):
        read(str(outside))
    with pytest.raises(PermissionError, match="secret workspace files"):
        read(".env")
    with pytest.raises(PermissionError, match="selected Host binding"):
        read("other.txt", workspace_id="other-workspace")


@pytest.mark.parametrize("deny_mode", ["unapproved", "blocked"])
def test_unapproved_or_blocked_file_pack_is_not_activated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    deny_mode: str,
) -> None:
    """A selected pack cannot become executable without current host trust."""
    monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
    _manager, profile, _approved, _user_data = _make_gui_profile(
        tmp_path,
        monkeypatch,
    )
    denied = _Approval(
        unapproved={FILE_INSPECT_PACK} if deny_mode == "unapproved" else None,
        blocked={FILE_INSPECT_PACK} if deny_mode == "blocked" else None,
    )
    plan = _resolve_gui_profile(profile, denied)
    assert FILE_INSPECT_PACK not in plan.effective_pack_set
    assert any(
        item.code == "pack_not_authorized" and item.subject == FILE_INSPECT_PACK
        for item in plan.diagnostics
    )

    registry = _register(plan, denied)
    with _active(plan):
        assert selected_global_providers(registry, FILE_INSPECT_CONTRACT) == ()
        with pytest.raises(
            GlobalContractUnavailable,
            match=r"expected one active provider for "
            + FILE_INSPECT_CONTRACT
            + r"; found 0",
        ):
            invoke_global_contract(
                registry,
                FILE_INSPECT_CONTRACT,
                "read",
                {"profile_id": PROFILE_ID, "workspace_id": "qa-workspace"},
            )


def test_tampered_file_pack_is_skipped_and_cannot_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Artifact-integrity failure must not leave a callable stale provider."""
    monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
    _manager, profile, approval, _user_data = _make_gui_profile(
        tmp_path,
        monkeypatch,
    )
    plan = _resolve_gui_profile(profile, approval)

    import core_runtime.capability_binding_registration as binding_module

    original_verify = binding_module.verify_declared_artifacts

    def tampered(pack_dir: Path, ecosystem_manifest: dict[str, Any]) -> tuple[bool, list[str]]:
        if Path(pack_dir).name == FILE_INSPECT_PACK:
            return False, ["fixture tampered artifact"]
        return original_verify(pack_dir, ecosystem_manifest)

    monkeypatch.setattr(binding_module, "verify_declared_artifacts", tampered)
    registry = InterfaceRegistry()
    registration = register_pack_binding_handlers(
        interface_registry=registry,
        approval_manager=approval,
        ecosystem_dir=str(ECOSYSTEM),
        effective_pack_ids=plan.effective_pack_set,
    )
    assert registration.ok is False
    assert FILE_INSPECT_PACK in registration.skipped
    assert registry.get(
        f"global_contract.provider.{FILE_INSPECT_CONTRACT}",
        strategy="all",
    ) == []

    with _active(plan):
        with pytest.raises(
            GlobalContractUnavailable,
            match=r"expected one active provider for "
            + FILE_INSPECT_CONTRACT
            + r"; found 0",
        ):
            invoke_global_contract(
                registry,
                FILE_INSPECT_CONTRACT,
                "read",
                {"profile_id": PROFILE_ID, "workspace_id": "qa-workspace"},
            )


def test_missing_or_duplicate_conversation_provider_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Global dispatch rejects both absent and ambiguous foundational owners."""
    monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
    _manager, profile, approval, _user_data = _make_gui_profile(
        tmp_path,
        monkeypatch,
        include_conversation_pack=True,
    )
    plan = _resolve_gui_profile(profile, approval)
    assert sum(
        provider.contract_id == CONVERSATION_CONTRACT
        for provider in plan.providers
    ) == 1

    missing_registry = InterfaceRegistry()
    with _active(plan):
        assert selected_global_providers(missing_registry, CONVERSATION_CONTRACT) == ()
        with pytest.raises(
            GlobalContractUnavailable,
            match=r"expected one active provider for "
            + CONVERSATION_CONTRACT
            + r"; found 0",
        ):
            invoke_global_contract(
                missing_registry,
                CONVERSATION_CONTRACT,
                "list",
                {"profile_id": PROFILE_ID},
            )

    registry = _register(plan, approval)
    key = f"global_contract.provider.{CONVERSATION_CONTRACT}"
    candidates = registry.get(key, strategy="all")
    assert len(candidates) == 1
    registry.register(key, dict(candidates[0]))
    with _active(plan):
        assert len(selected_global_providers(registry, CONVERSATION_CONTRACT)) == 2
        with pytest.raises(
            GlobalContractUnavailable,
            match=r"expected one active provider for "
            + CONVERSATION_CONTRACT
            + r"; found 2",
        ):
            invoke_global_contract(
                registry,
                CONVERSATION_CONTRACT,
                "list",
                {"profile_id": PROFILE_ID},
            )
