from __future__ import annotations

import json
from collections.abc import Callable

from ecosystem.defaultspack.backend.sandbox.gui_sandbox import GUISandbox
from ecosystem.defaultspack.backend.sandbox.models import ProviderInstance, ReconcileResult
from ecosystem.defaultspack.backend.sandbox.provider_registry import ProviderRegistry
from ecosystem.defaultspack.backend.sandbox.sandbox_manager import SandboxManager
from ecosystem.defaultspack.backend.sandbox.testing.fake_provider import FakeRuntimeProvider
from ecosystem.defaultspack.backend.sandbox.errors import SandboxContractError
from ecosystem.defaultspack.domain.coding.workspace_store import WorkspaceStore


def _registry(
    *,
    capabilities: set[str] | None = None,
    ready: bool = True,
    sandbox_id_factory: Callable[[], str] | None = None,
) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        FakeRuntimeProvider(
            provider_id="fake-runtime",
            capabilities=capabilities
            or {
                "sandbox.exec",
                "sandbox.files",
                "sandbox.resource_limits",
                "sandbox.network_policy",
                "sandbox.desktop",
                "sandbox.desktop_input",
                "sandbox.snapshot",
            },
            ready=ready,
            sandbox_id_factory=sandbox_id_factory,
        )
    )
    return registry


def _manager(
    tmp_path,
    *,
    capabilities: set[str] | None = None,
    ready: bool = True,
    gui_backend=None,
    sandbox_id_factory: Callable[[], str] | None = None,
) -> SandboxManager:
    return SandboxManager(
        state_dir=tmp_path,
        gui_backend=gui_backend,
        provider_registry=_registry(capabilities=capabilities, ready=ready, sandbox_id_factory=sandbox_id_factory),
    )


def _trusted_workspace(tmp_path, monkeypatch, *, workspace_id: str = "workspace-1"):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH", str(tmp_path / "workspaces.json"))
    root = tmp_path / "workspace"
    root.mkdir(exist_ok=True)
    WorkspaceStore().create(root, workspace_id=workspace_id, trusted=True)
    return root


def test_sandbox_create_fails_closed_without_registered_provider(tmp_path):
    manager = SandboxManager(state_dir=tmp_path)

    created = manager.create(display=False)

    assert created["ok"] is False
    assert created["status_code"] == 503
    assert created["code"] == "RUNTIME_PROVIDER_UNAVAILABLE"
    assert "No registered runtime provider" in created["error"]


def test_sandbox_registry_persists_instances_and_lifecycle(tmp_path):
    manager = _manager(tmp_path, capabilities={"sandbox.exec", "sandbox.files", "sandbox.resource_limits"})

    created = manager.create(image="ubuntu:24.04", display=False)

    assert created["ok"] is True
    assert created["created"] is True
    assert created["status"] == "ready"
    sandbox_id = created["sandbox_id"]
    registry_path = tmp_path / "sandboxes.json"
    assert registry_path.is_file()

    reloaded = _manager(tmp_path, capabilities={"sandbox.exec", "sandbox.files", "sandbox.resource_limits"})
    status = reloaded.status(sandbox_id)
    assert status["ok"] is True
    assert status["sandbox_id"] == sandbox_id
    assert status["image"] == "ubuntu:24.04"
    assert status["display"] is False
    assert status["status"] == "ready"
    assert status["state"] == "ready"
    assert status["provider_id"] == "fake-runtime"
    assert status["template_id"] == "tool.ephemeral"

    destroyed = reloaded.destroy(sandbox_id)
    assert destroyed == {
        "ok": True,
        "destroyed": True,
        "sandbox_id": sandbox_id,
        "status": "destroyed",
        "state": "destroyed",
    }

    lifecycle = _manager(tmp_path, capabilities={"sandbox.exec", "sandbox.files"}).status(sandbox_id)
    assert lifecycle["status"] == "destroyed"
    assert lifecycle["destroyed_at"] is not None
    assert lifecycle["updated_at"] >= lifecycle["created_at"]


def test_sandbox_registry_reconciles_missing_runtime_session_to_stopped(tmp_path):
    registry_path = tmp_path / "sandboxes.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "instances": {
                    "seat-1": {
                        "sandbox_id": "seat-1",
                        "name": "Desktop",
                        "image": "ubuntu:22.04",
                        "display": True,
                        "template_id": "desktop.ubuntu",
                        "provider_id": "fake-runtime",
                        "provider_instance_id": "fake-seat-1",
                        "runtime_id": "fake-runtime",
                        "state": "ready",
                        "created_at": 10,
                        "updated_at": 11,
                        "desktop_spec": {"enabled": True, "width": 800, "height": 600},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    class ReconcileStoppedProvider(FakeRuntimeProvider):
        def reconcile(self, persisted: ProviderInstance) -> ReconcileResult:
            return ReconcileResult(
                instance=ProviderInstance(
                    provider_id=persisted.provider_id,
                    provider_instance_id=persisted.provider_instance_id,
                    sandbox_id=persisted.sandbox_id,
                    runtime_id=persisted.runtime_id,
                    state="stopped",
                    opaque_state=persisted.opaque_state,
                    generation=persisted.generation,
                ),
                changed=True,
            )

    registry = ProviderRegistry()
    registry.register(ReconcileStoppedProvider(provider_id="fake-runtime"))

    manager = SandboxManager(state_dir=tmp_path, provider_registry=registry)
    status = manager.status("seat-1")
    persisted = json.loads(registry_path.read_text(encoding="utf-8"))

    assert status["status"] == "stopped"
    assert status["stopped_at"] is not None
    assert "startup reconcile" in status["last_error"]
    assert persisted["instances"]["seat-1"]["state"] == "stopped"


def test_sandbox_create_rolls_back_provider_instance_when_start_fails(tmp_path):
    class StartFailProvider(FakeRuntimeProvider):
        def start(self, instance: ProviderInstance) -> ProviderInstance:
            raise SandboxContractError("FAKE_START_FAILED", "start failed", status_code=503)

    provider = StartFailProvider(
        provider_id="fake-runtime",
        capabilities={"sandbox.exec", "sandbox.files", "sandbox.resource_limits"},
    )
    registry = ProviderRegistry()
    registry.register(provider)
    manager = SandboxManager(state_dir=tmp_path, provider_registry=registry)

    created = manager.create(display=False, provider_id="fake-runtime", template_id="tool.ephemeral")

    assert created["ok"] is False
    assert created["code"] == "FAKE_START_FAILED"
    assert provider.instances == {}
    assert manager.list_instances() == []


def test_sandbox_unknown_template_is_rejected(tmp_path):
    manager = _manager(tmp_path, capabilities={"sandbox.exec", "sandbox.files", "sandbox.resource_limits"})

    created = manager.create(display=False, provider_id="fake-runtime", template_id="missing.template")

    assert created["ok"] is False
    assert created["code"] == "SANDBOX_TEMPLATE_NOT_FOUND"


def test_sandbox_create_rejects_endpoint_template_kind_mismatch(tmp_path):
    manager = _manager(tmp_path)

    desktop_template_on_sandbox_endpoint = manager.create(
        display=False,
        provider_id="fake-runtime",
        template_id="desktop.coding",
    )
    tool_template_on_desktop_endpoint = manager.create(
        display=True,
        provider_id="fake-runtime",
        template_id="tool.ephemeral",
    )

    assert desktop_template_on_sandbox_endpoint["ok"] is False
    assert desktop_template_on_sandbox_endpoint["code"] == "SANDBOX_TEMPLATE_KIND_MISMATCH"
    assert tool_template_on_desktop_endpoint["ok"] is False
    assert tool_template_on_desktop_endpoint["code"] == "SANDBOX_TEMPLATE_NOT_DESKTOP"


def test_sandbox_template_policy_and_nested_fields_survive_reload(tmp_path, monkeypatch):
    workspace_root = _trusted_workspace(tmp_path, monkeypatch)
    manager = _manager(tmp_path)

    created = manager.create(
        display=True,
        provider_id="fake-runtime",
        template_id="desktop.coding",
        access_owner_id="local-user",
        assigned_agent_id="agent-1",
        workspace_id="workspace-1",
        workspace_access="read_only",
    )
    assert created["ok"] is True

    sandbox_id = created["sandbox_id"]
    status = manager.status(sandbox_id)
    assert status["template_id"] == "desktop.coding"
    assert status["network_policy"]["mode"] == "project_policy_or_first_use_approval"
    assert status["resource_limits"]["memory_mb"] == 4096
    assert status["workspace_binding"]["mode"] == "read_only"
    assert status["workspace_binding"]["root"] == str(workspace_root)
    assert status["assigned_agent_id"] == "agent-1"
    assert "desktop.mcp.install.request" in status["capabilities"]

    reloaded = _manager(tmp_path)
    reloaded_status = reloaded.status(sandbox_id)

    assert reloaded_status["network_policy"]["mode"] == "project_policy_or_first_use_approval"
    assert reloaded_status["resource_limits"]["timeout_ms"] == 14_400_000
    assert reloaded_status["desktop_spec"]["width"] == 1440
    assert reloaded_status["assigned_agent_id"] == "agent-1"
    assert reloaded_status["lifecycle_policy"]["ttl_seconds"] == 14_400
    assert reloaded_status["lifecycle_policy"]["destroy_on_exit"] is False


def test_desktop_create_spec_carries_user_selected_runtime_context(tmp_path, monkeypatch):
    workspace_root = _trusted_workspace(tmp_path, monkeypatch)
    provider = FakeRuntimeProvider(
        capabilities={
            "sandbox.exec",
            "sandbox.files",
            "sandbox.overlay_workspace",
            "sandbox.port_forward",
            "sandbox.resource_limits",
            "sandbox.network_policy",
            "sandbox.desktop",
            "sandbox.desktop_input",
            "sandbox.snapshot",
            "desktop.app.install",
            "desktop.browser.launch",
            "desktop.mcp.install.request",
            "sandbox.network.allowlist",
        },
    )
    registry = ProviderRegistry()
    registry.register(provider)
    manager = SandboxManager(state_dir=tmp_path, provider_registry=registry)

    created = manager.create(
        display=True,
        provider_id="fake",
        template_id="desktop.coding",
        access_owner_id="local-user",
        role="browser operator",
        rules={"rule_ids": ["browser-only"], "instructions": "Open only the requested URL."},
        assigned_agent_id="agent-1",
        workspace_id="workspace-1",
        workspace_access="read_only",
        provisioning={"apps": ["chrome"], "mcp_servers": ["playwright"]},
        starter="browser_url",
        browser_url="https://example.com/task",
    )

    assert created["ok"] is True
    assert len(provider.create_specs) == 1
    spec = provider.create_specs[0]
    assert spec.workspace_binding.workspace_id == "workspace-1"
    assert spec.workspace_binding.mode == "read_only"
    assert spec.workspace_binding.root == str(workspace_root)
    assert spec.metadata["startup"] == {
        "starter": "browser_url",
        "browser_url": "https://example.com/task",
    }
    assert spec.metadata["desktop_rules"]["role"] == "browser operator"
    assert spec.metadata["desktop_rules"]["instructions"] == "Open only the requested URL."
    assert spec.metadata["desktop_provisioning"]["apps"] == ["chrome"]
    assert spec.metadata["desktop_provisioning"]["mcp_servers"] == ["playwright"]
    assert spec.metadata["assigned_agent_id"] == "agent-1"

    status = manager.status(created["sandbox_id"])
    assert status["desktop_spec"]["preset"] == "browser_url"
    assert status["provider_opaque_state"]["metadata"]["startup"]["browser_url"] == "https://example.com/task"
    assert status["provider_opaque_state"]["workspace_binding"]["workspace_id"] == "workspace-1"

    reloaded = SandboxManager(state_dir=tmp_path, provider_registry=registry)
    reloaded_status = reloaded.status(created["sandbox_id"])
    assert reloaded_status["provider_opaque_state"]["metadata"]["desktop_provisioning"]["apps"] == ["chrome"]
    assert reloaded_status["provider_opaque_state"]["metadata"]["assigned_agent_id"] == "agent-1"


def test_desktop_create_rejects_invalid_browser_url_starter(tmp_path):
    manager = _manager(tmp_path)

    created = manager.create(
        display=True,
        provider_id="fake-runtime",
        template_id="desktop.ubuntu",
        access_owner_id="local-user",
        starter="browser_url",
        browser_url="file:///etc/passwd",
    )

    assert created["ok"] is False
    assert created["code"] == "DESKTOP_BROWSER_URL_INVALID"
    assert created["status_code"] == 400


def test_sandbox_lifecycle_policy_enforces_idle_stop_or_destroy(tmp_path):
    manager = _manager(
        tmp_path,
        capabilities={
            "sandbox.exec",
            "sandbox.files",
            "sandbox.overlay_workspace",
            "sandbox.port_forward",
            "sandbox.resource_limits",
            "sandbox.network_policy",
        },
    )
    coding = manager.create(display=False, provider_id="fake-runtime", template_id="coding.python")
    assert coding["ok"] is True
    coding_status = manager.status(coding["sandbox_id"])

    stop_results = manager.enforce_lifecycle(now=float(coding_status["started_at"]) + 14_401)

    assert stop_results[0]["lifecycle_action"] == "stop"
    assert manager.status(coding["sandbox_id"])["state"] == "stopped"

    desktop_manager = _manager(
        tmp_path / "desktop",
        capabilities={"sandbox.desktop", "sandbox.desktop_input", "sandbox.snapshot"},
    )
    desktop = desktop_manager.create(
        display=True,
        provider_id="fake-runtime",
        template_id="desktop.linux_native",
        access_owner_id="local-user",
    )
    assert desktop["ok"] is True
    desktop_status = desktop_manager.status(desktop["sandbox_id"])

    destroy_results = desktop_manager.enforce_lifecycle(now=float(desktop_status["started_at"]) + 14_401)

    assert destroy_results[0]["lifecycle_action"] == "destroy"
    assert desktop_manager.status(desktop["sandbox_id"])["state"] == "destroyed"


def test_sandbox_lifecycle_start_stop_restart_uses_provider_state(tmp_path):
    manager = _manager(tmp_path, capabilities={"sandbox.exec", "sandbox.files", "sandbox.resource_limits"})
    sandbox_id = manager.create(image="ubuntu:24.04", display=False)["sandbox_id"]

    stopped = manager.stop(sandbox_id)
    stopped_status = manager.status(sandbox_id)
    start = manager.start(sandbox_id)
    restart = manager.restart(sandbox_id)

    assert stopped["ok"] is True
    assert stopped["state"] == "stopped"
    assert stopped_status["state"] == "stopped"
    assert start["ok"] is True
    assert start["state"] == "ready"
    assert restart["ok"] is True
    assert restart["state"] == "ready"
    assert restart["generation"] > stopped["generation"]


def test_sandbox_exec_is_guest_agent_only_and_template_gated(tmp_path):
    manager = _manager(tmp_path, capabilities={"sandbox.exec", "sandbox.files", "sandbox.resource_limits"})
    sandbox_id = manager.create(image="ubuntu:24.04", display=False)["sandbox_id"]

    executed = manager.exec(
        sandbox_id,
        {"argv": ["python", "--version"], "cwd": ".", "client_request_id": "exec-1"},
    )
    raw_command = manager.exec(
        sandbox_id,
        {"command": "python --version", "client_request_id": "exec-2"},
    )

    desktop_only = _manager(
        tmp_path / "desktop-only",
        capabilities={"sandbox.desktop", "sandbox.desktop_input", "sandbox.snapshot"},
    )
    desktop = desktop_only.create(
        display=True,
        provider_id="fake-runtime",
        template_id="desktop.linux_native",
        access_owner_id="local-user",
    )
    denied = desktop_only.exec(
        desktop["sandbox_id"],
        {"argv": ["python", "--version"], "cwd": ".", "client_request_id": "exec-3"},
    )

    assert executed["ok"] is True
    assert executed["argv"] == ["python", "--version"]
    assert raw_command["ok"] is False
    assert raw_command["code"] == "RAW_COMMAND_REJECTED"
    assert denied["ok"] is False
    assert denied["code"] == "SANDBOX_OPERATION_NOT_ALLOWED"


def test_ai_desktop_input_rate_limit_is_actor_scoped(tmp_path):
    manager = _manager(tmp_path)
    created = manager.create(
        display=True,
        provider_id="fake-runtime",
        template_id="desktop.ubuntu",
        assigned_agent_id="agent-1",
        access_owner_id="local-user",
    )
    assert created["ok"] is True
    seat_id = created["sandbox_id"]

    last_ok = None
    for index in range(30):
        last_ok = manager.desktop_input(
            seat_id,
            {"action": "click", "client_action_id": f"ai-{index}", "x": 1, "y": 1, "agent_id": "agent-1"},
            actor="ai",
        )
    limited = manager.desktop_input(
        seat_id,
        {"action": "click", "client_action_id": "ai-limited", "x": 1, "y": 1, "agent_id": "agent-1"},
        actor="ai",
    )
    other_agent = manager.desktop_input(
        seat_id,
        {"action": "click", "client_action_id": "ai-other", "x": 1, "y": 1, "agent_id": "agent-2"},
        actor="ai",
    )

    assert last_ok is not None and last_ok["ok"] is True
    assert limited["ok"] is False
    assert limited["code"] == "DESKTOP_INPUT_RATE_LIMITED"
    assert other_agent["ok"] is False
    assert other_agent["code"] == "DESKTOP_AGENT_NOT_ASSIGNED"
    audit_codes = [event["code"] for event in manager.read_desktop_audit_events(limit=4)]
    assert "DESKTOP_INPUT_RATE_LIMITED" in audit_codes
    assert "DESKTOP_AGENT_NOT_ASSIGNED" in audit_codes


def test_sandbox_file_patch_and_port_contracts_fail_closed_until_guest_services_exist(tmp_path):
    manager = _manager(
        tmp_path,
        capabilities={
            "sandbox.exec",
            "sandbox.files",
            "sandbox.overlay_workspace",
            "sandbox.port_forward",
            "sandbox.resource_limits",
            "sandbox.network_policy",
        },
    )
    sandbox_id = manager.create(display=False, provider_id="fake-runtime", template_id="coding.python")["sandbox_id"]

    file_patch = manager.apply_file_patch(sandbox_id, {"patch": []})
    port = manager.expose_port(sandbox_id, {"port": 3000})

    assert file_patch["ok"] is False
    assert file_patch["code"] == "SANDBOX_FILES_NOT_READY"
    assert file_patch["status_code"] == 501
    assert port["ok"] is False
    assert port["code"] == "SANDBOX_PORTS_NOT_READY"
    assert port["status_code"] == 501


def test_desktop_resolution_is_bounded_before_provider_start(tmp_path):
    manager = _manager(tmp_path)

    created = manager.create(
        display=True,
        provider_id="fake-runtime",
        template_id="desktop.ubuntu",
        width=20_000,
        height=20_000,
        access_owner_id="local-user",
    )

    assert created["ok"] is False
    assert created["code"] == "DESKTOP_RESOLUTION_LIMIT_EXCEEDED"
    assert created["status_code"] == 400


def test_sandbox_screenshot_fails_closed_without_backend(tmp_path):
    manager = _manager(tmp_path)
    sandbox_id = manager.create(access_owner_id="local-user")["sandbox_id"]

    result = manager.screenshot(sandbox_id)

    assert result["ok"] is False
    assert result["code"] == "SANDBOX_BACKEND_UNAVAILABLE"
    assert result["status_code"] == 503
    assert result["sandbox_id"] == sandbox_id
    assert result["status"] == "ready"
    assert result["gui_backend"] is False
    assert result["action"] == "screenshot"
    assert "screenshot" in result["error"]


def test_sandbox_not_found_and_destroyed_errors_are_clear(tmp_path):
    manager = _manager(tmp_path)

    missing = manager.screenshot("missing-sandbox")
    assert missing["ok"] is False
    assert missing["status_code"] == 404
    assert missing["code"] == "SANDBOX_NOT_FOUND"
    assert missing["sandbox_id"] == "missing-sandbox"
    assert "Sandbox not found" in missing["error"]

    sandbox_id = manager.create(access_owner_id="local-user")["sandbox_id"]
    manager.destroy(sandbox_id)

    screenshot = manager.screenshot(sandbox_id)
    assert screenshot["ok"] is False
    assert screenshot["status_code"] == 409
    assert screenshot["code"] == "SANDBOX_NOT_RUNNING"
    assert screenshot["status"] == "destroyed"
    assert "destroyed" in screenshot["error"]

    click = manager.click(sandbox_id, 10, 20)
    assert click["ok"] is False
    assert click["status_code"] == 409
    assert click["code"] == "SANDBOX_NOT_RUNNING"


def test_sandbox_destroy_marks_failed_when_backend_teardown_fails(tmp_path):
    class Backend:
        def __init__(self):
            self.destroyed = []

        def destroy_session(self, sandbox_id):
            self.destroyed.append(sandbox_id)
            return {"ok": False, "error": "teardown refused"}

    backend = Backend()
    manager = _manager(tmp_path, gui_backend=backend)
    sandbox_id = manager.create(access_owner_id="local-user")["sandbox_id"]

    result = manager.destroy(sandbox_id)

    assert result["ok"] is False
    assert result["destroyed"] is False
    assert result["code"] == "SANDBOX_BACKEND_DESTROY_FAILED"
    assert result["status"] == "failed"
    assert result["error"] == "teardown refused"
    assert backend.destroyed == [sandbox_id]

    persisted = _manager(tmp_path).status(sandbox_id)
    assert persisted["status"] == "failed"
    assert persisted["destroyed_at"] is None
    assert persisted["last_error"] == "teardown refused"


def test_sandbox_input_actions_fail_closed_without_backend(tmp_path):
    manager = _manager(tmp_path)
    sandbox_id = manager.create(access_owner_id="local-user")["sandbox_id"]

    click = manager.click(sandbox_id, 10, 20)
    typed = manager.type_text(sandbox_id, "hello")
    scroll = manager.scroll(sandbox_id, direction="up", amount=2)

    for result, action, success_key in (
        (click, "click", "clicked"),
        (typed, "type_text", "typed"),
        (scroll, "scroll", "scrolled"),
    ):
        assert result["ok"] is False
        assert result["code"] == "SANDBOX_BACKEND_UNAVAILABLE"
        assert result["status_code"] == 503
        assert result["sandbox_id"] == sandbox_id
        assert result["status"] == "ready"
        assert result["gui_backend"] is False
        assert result["action"] == action
        assert success_key not in result
        assert "recorded" not in result
        assert "backend unavailable" in result["error"]

    status = manager.status(sandbox_id)
    assert status["ok"] is True
    assert status["status"] == "ready"
    assert status["last_error"] is None


def test_sandbox_input_actions_route_to_backend_before_reporting_success(tmp_path):
    class Backend:
        def __init__(self):
            self.calls = []

        def click(self, sandbox_id, x, y):
            self.calls.append(("click", sandbox_id, x, y))
            return {"ok": True, "backend_action": "click"}

        def type_text(self, sandbox_id, text):
            self.calls.append(("type_text", sandbox_id, text))
            return {"ok": True, "backend_action": "type_text"}

        def scroll(self, sandbox_id, amount):
            self.calls.append(("scroll", sandbox_id, amount))
            return {"ok": True, "backend_action": "scroll"}

    backend = Backend()
    manager = _manager(tmp_path, gui_backend=backend)
    sandbox_id = manager.create(access_owner_id="local-user")["sandbox_id"]

    click = manager.click(sandbox_id, 10, 20)
    typed = manager.type_text(sandbox_id, "hello")
    scroll = manager.scroll(sandbox_id, direction="up", amount=2)

    assert click["ok"] is True
    assert click["clicked"] is True
    assert click["gui_backend"] is True
    assert click["x"] == 10
    assert click["y"] == 20
    assert typed["ok"] is True
    assert typed["typed"] is True
    assert typed["text"] == "hello"
    assert scroll["ok"] is True
    assert scroll["scrolled"] is True
    assert scroll["direction"] == "up"
    assert scroll["amount"] == 2
    assert backend.calls == [
        ("click", sandbox_id, 10, 20),
        ("type_text", sandbox_id, "hello"),
        ("scroll", sandbox_id, 2),
    ]
    assert manager.status(sandbox_id)["last_activity_at"] is not None


def test_sandbox_manager_uses_explicit_test_gui_backend_for_input_actions(tmp_path):
    backend = GUISandbox()
    session = backend.create_session("test desktop")
    manager = _manager(tmp_path, gui_backend=backend, sandbox_id_factory=lambda: session.session_id)
    sandbox_id = manager.create(access_owner_id="local-user")["sandbox_id"]

    result = manager.click(sandbox_id, 1, 2)

    assert result["ok"] is True
    assert result["clicked"] is True
    assert result["gui_backend"] is True
    stored = backend.get_session(sandbox_id)
    assert stored is session
    assert stored.events[-1]["action"] == "click"
    assert stored.events[-1]["x"] == 1
    assert stored.events[-1]["y"] == 2


def test_sandbox_input_backend_failures_do_not_gain_success_flags(tmp_path):
    class Backend:
        def click(self, sandbox_id, x, y):
            return {"ok": False, "error": "window missing", "clicked": True, "recorded": True}

    manager = _manager(tmp_path, gui_backend=Backend())
    sandbox_id = manager.create(access_owner_id="local-user")["sandbox_id"]

    result = manager.click(sandbox_id, 10, 20)

    assert result["ok"] is False
    assert result["code"] == "SANDBOX_BACKEND_ACTION_FAILED"
    assert result["status_code"] == 502
    assert result["sandbox_id"] == sandbox_id
    assert result["gui_backend"] is True
    assert result["action"] == "click"
    assert result["error"] == "window missing"
    assert "clicked" not in result
    assert "recorded" not in result
    assert manager.status(sandbox_id)["last_activity_at"] is None


def test_sandbox_state_dir_env_override_is_used(monkeypatch, tmp_path):
    override = tmp_path / "local-state"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SANDBOX_STATE_DIR", str(override))

    manager = SandboxManager(provider_registry=_registry())
    sandbox_id = manager.create(access_owner_id="local-user")["sandbox_id"]

    registry_path = override / "sandboxes.json"
    assert manager.registry_path == registry_path
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert sandbox_id in payload["instances"]
    assert SandboxManager(provider_registry=_registry()).status(sandbox_id)["status"] == "ready"


def test_legacy_ready_registry_records_are_not_treated_as_live(tmp_path):
    registry_path = tmp_path / "sandboxes.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instances": {
                    "legacy-seat": {
                        "sandbox_id": "legacy-seat",
                        "image": "ubuntu:22.04",
                        "display": True,
                        "status": "ready",
                        "created_at": 10,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    manager = SandboxManager(state_dir=tmp_path)
    status = manager.status("legacy-seat")
    screenshot = manager.screenshot("legacy-seat")

    assert status["ok"] is True
    assert status["status"] == "stopped"
    assert status["provider_id"] == "legacy_placeholder"
    assert "fake-ready" in status["last_error"]
    assert screenshot["ok"] is False
    assert screenshot["code"] == "SANDBOX_NOT_RUNNING"
    assert screenshot["status"] == "stopped"
