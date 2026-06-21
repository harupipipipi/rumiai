from __future__ import annotations

import pytest

from ecosystem.defaultspack.backend.sandbox.control_lease import ControlLeaseManager
from ecosystem.defaultspack.backend.sandbox.errors import (
    DESKTOP_CONTROL_CONFLICT,
    DESKTOP_LEASE_EXPIRED,
    DESKTOP_LEASE_REQUIRED,
    INVALID_EXEC_REQUEST,
    RAW_COMMAND_REJECTED,
    SandboxContractError,
)
from ecosystem.defaultspack.backend.sandbox.frame_cache import FrameCache
from ecosystem.defaultspack.backend.sandbox.guest.protocol import DesktopInputRequest, GuestExecRequest
from ecosystem.defaultspack.backend.sandbox.models import (
    DesktopSpec,
    FilesystemPolicy,
    LifecyclePolicy,
    NetworkPolicy,
    ResolvedSandboxTemplate,
    ResourceLimits,
    RuntimeRequirements,
    SecretsPolicy,
)
from ecosystem.defaultspack.backend.sandbox.provider_registry import ProviderRegistry
from ecosystem.defaultspack.backend.sandbox.testing.fake_guest_agent import FakeGuestAgent
from ecosystem.defaultspack.backend.sandbox.testing.fake_provider import FakeRuntimeProvider


class Clock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_exec_protocol_rejects_raw_command_strings_and_accepts_argv() -> None:
    with pytest.raises(SandboxContractError) as raw:
        GuestExecRequest.from_payload({"command": "python -m pytest -q", "client_request_id": "req-1"})
    assert raw.value.code == RAW_COMMAND_REJECTED

    with pytest.raises(SandboxContractError) as argv_string:
        GuestExecRequest.from_payload({"argv": "python -m pytest -q", "client_request_id": "req-2"})
    assert argv_string.value.code == INVALID_EXEC_REQUEST

    with pytest.raises(SandboxContractError):
        GuestExecRequest.from_payload({"argv": ["python"], "cwd": "../outside", "client_request_id": "req-3"})

    request = GuestExecRequest.from_payload(
        {
            "argv": ["python", "-m", "pytest", "-q"],
            "cwd": "tests",
            "env": {"PYTHONUNBUFFERED": "1"},
            "timeout_ms": 120_000,
            "stdin": None,
            "client_request_id": "req-4",
        }
    )

    assert request.argv == ("python", "-m", "pytest", "-q")
    assert request.to_agent_payload()["argv"] == ["python", "-m", "pytest", "-q"]
    assert "command" not in request.to_agent_payload()


def test_fake_guest_agent_keeps_exec_as_argv_only() -> None:
    agent = FakeGuestAgent()

    result = agent.exec(
        "sandbox-1",
        {"argv": ["echo", "hello"], "cwd": ".", "env": {}, "timeout_ms": 1000, "client_request_id": "exec-1"},
    )

    assert result["ok"] is True
    assert result["argv"] == ["echo", "hello"]
    assert agent.exec_requests[0].argv == ("echo", "hello")

    with pytest.raises(SandboxContractError) as raw:
        agent.exec("sandbox-1", {"command": "echo hello", "client_request_id": "exec-2"})
    assert raw.value.code == RAW_COMMAND_REJECTED


def test_provider_registry_uses_status_and_required_capabilities() -> None:
    exec_provider = FakeRuntimeProvider(provider_id="fake-exec", capabilities={"sandbox.exec"})
    desktop_provider = FakeRuntimeProvider(
        provider_id="fake-desktop",
        capabilities={"sandbox.exec", "sandbox.desktop", "sandbox.desktop_input"},
    )
    registry = ProviderRegistry()
    registry.register(exec_provider)
    registry.register(desktop_provider)

    resolved = registry.resolve(
        "auto",
        RuntimeRequirements(required_capabilities=frozenset({"sandbox.desktop_input"})),
    )

    assert resolved.provider_id == "fake-desktop"
    status = registry.doctor(
        "fake-exec",
        RuntimeRequirements(required_capabilities=frozenset({"sandbox.desktop_input"})),
    )
    assert status.ready is False
    assert status.missing_requirements == ("sandbox.desktop_input",)


def test_control_lease_conflict_expiry_and_token_hash_storage() -> None:
    clock = Clock()
    manager = ControlLeaseManager(ttl_seconds=30, time_fn=clock, token_factory=lambda: "secret-token")

    grant = manager.acquire("seat-1", "human-1")
    assert grant.token == "secret-token"

    snapshot = manager.debug_snapshot()
    assert "token_hash" in snapshot["seat-1"]
    assert "token" not in snapshot["seat-1"]
    assert "secret-token" not in str(snapshot)

    with pytest.raises(SandboxContractError) as conflict:
        manager.acquire("seat-1", "human-2")
    assert conflict.value.code == DESKTOP_CONTROL_CONFLICT

    with pytest.raises(SandboxContractError) as ai_conflict:
        manager.validate_ai_input("seat-1")
    assert ai_conflict.value.code == DESKTOP_CONTROL_CONFLICT

    with pytest.raises(SandboxContractError) as missing:
        manager.validate_human_input("seat-1", None)
    assert missing.value.code == DESKTOP_LEASE_REQUIRED

    assert manager.validate_human_input("seat-1", grant.token).owner_id == "human-1"
    clock.advance(10)
    renewed = manager.renew("seat-1", "human-1", grant.token)
    assert renewed.expires_at == clock.now + 30

    clock.advance(31)
    with pytest.raises(SandboxContractError) as expired:
        manager.validate_human_input("seat-1", grant.token)
    assert expired.value.code == DESKTOP_LEASE_EXPIRED

    next_grant = manager.acquire("seat-1", "human-2")
    assert next_grant.owner_id == "human-2"


def test_desktop_input_requires_valid_lease_and_redacts_typed_text_from_audit() -> None:
    clock = Clock()
    lease_manager = ControlLeaseManager(ttl_seconds=30, time_fn=clock, token_factory=lambda: "lease-token")
    agent = FakeGuestAgent(lease_manager=lease_manager, width=800, height=600)
    grant = lease_manager.acquire("seat-1", "human-1")

    with pytest.raises(SandboxContractError) as missing:
        DesktopInputRequest.from_payload({"action": "click", "client_action_id": "act-1", "x": 1, "y": 2})
    assert missing.value.code == DESKTOP_LEASE_REQUIRED

    with pytest.raises(SandboxContractError) as ai_conflict:
        agent.desktop_input("sandbox-1", "seat-1", {"action": "key", "client_action_id": "ai-1", "key": "Enter"}, actor="ai")
    assert ai_conflict.value.code == DESKTOP_CONTROL_CONFLICT

    result = agent.desktop_input(
        "sandbox-1",
        "seat-1",
        {
            "action": "type_text",
            "client_action_id": "act-2",
            "lease_token": grant.token,
            "text": "do not audit this",
        },
    )

    assert result["ok"] is True
    assert agent.desktop_inputs[0].text == "do not audit this"
    assert "text" not in agent.audit_events[0]
    assert "lease_token" not in agent.audit_events[0]


def test_frame_cache_after_seq_returns_not_modified_without_advancing_frame() -> None:
    clock = Clock()
    cache = FrameCache(time_fn=clock)

    first = cache.put_frame("seat-1", b"frame-one", content_type="image/png", width=2, height=2)
    not_modified = cache.get_frame("seat-1", after_seq=first.frame_seq)

    assert not_modified.status_code == 204
    assert not_modified.not_modified is True
    assert not_modified.frame is None
    assert cache.last_metadata("seat-1")["frame_seq"] == first.frame_seq

    again = cache.get_frame("seat-1", after_seq=first.frame_seq)
    assert again.status_code == 204
    assert cache.last_metadata("seat-1")["frame_seq"] == first.frame_seq

    clock.advance(1)
    second = cache.put_frame("seat-1", b"frame-two", content_type="image/png", width=2, height=2)
    fetched = cache.get_frame("seat-1", after_seq=first.frame_seq)

    assert second.frame_seq == first.frame_seq + 1
    assert fetched.status_code == 200
    assert fetched.frame == second


def test_fake_provider_create_lifecycle_is_local_only_contract_state() -> None:
    provider = FakeRuntimeProvider(provider_id="fake-runtime", capabilities={"sandbox.exec", "sandbox.desktop"})
    template = _template()

    instance = provider.create(
        _create_spec(template),
    )
    started = provider.start(instance)
    provider.stop(started)
    reconciled = provider.reconcile(started)
    provider.destroy(started)

    assert instance.provider_id == "fake-runtime"
    assert started.state == "ready"
    assert reconciled.instance.state == "stopped"
    assert started.provider_instance_id not in provider.instances


def test_defaultspack_runtime_routes_return_honest_unavailable_state() -> None:
    from ecosystem.defaultspack.blocks.sandbox import api
    from ecosystem.defaultspack.transport.registry import canonical_http_route_specs

    routes = {(spec.method, spec.pattern, spec.block_module) for spec in canonical_http_route_specs()}

    assert ("GET", "/api/runtime/providers", "blocks.sandbox.api") in routes
    assert ("POST", "/api/runtime/ensure", "blocks.sandbox.api") in routes
    assert ("GET", "/api/sandbox/templates", "blocks.sandbox.api") in routes
    assert ("GET", "/api/desktops", "blocks.sandbox.api") in routes
    providers = api.run({"_handler": "runtime_providers"}, {})
    doctor = api.run({"_handler": "runtime_doctor"}, {})
    ensure = api.run({"_handler": "runtime_ensure"}, {})
    templates = api.run({"_handler": "sandbox_templates"}, {})
    desktops = api.run({"_handler": "desktops_list"}, {})

    assert providers["status"] == "ok"
    assert providers["data"]["providers"][0]["status"] == "needs_setup"
    assert doctor["data"]["status"] == "needs_setup"
    assert ensure["data"]["status"] == "failed"
    assert ensure["data"]["error"]["code"] == "MANAGED_RUNTIME_NOT_READY"
    assert {template["template_id"] for template in templates["data"]["templates"]} >= {"desktop.ubuntu", "tool.ephemeral"}
    assert desktops["data"]["desktops"] == []


def test_runtime_mutation_routes_are_local_guard_sensitive() -> None:
    from ecosystem.defaultspack.domain.safety.local_guard import is_sensitive_coding_path

    assert is_sensitive_coding_path("/api/runtime/ensure", "POST") is True
    assert is_sensitive_coding_path("/api/runtime/operations/op-1/cancel", "POST") is True
    assert is_sensitive_coding_path("/api/desktops", "POST") is True
    assert is_sensitive_coding_path("/api/desktops/seat-1/input", "POST") is True


def _template() -> ResolvedSandboxTemplate:
    return ResolvedSandboxTemplate(
        template_id="desktop.ubuntu",
        template_version="1",
        runtime_os="linux",
        provider_requirements=frozenset({"sandbox.exec", "sandbox.desktop"}),
        packages=(),
        desktop=DesktopSpec(enabled=True, width=800, height=600),
        filesystem=FilesystemPolicy(),
        network=NetworkPolicy(mode="off"),
        secrets=SecretsPolicy(mode="denied"),
        resources=ResourceLimits(cpu_count=1, memory_mb=1024),
        lifecycle=LifecyclePolicy(ttl_seconds=900),
        allowed_operations=frozenset({"exec", "desktop.input"}),
        source_template_ids=("desktop.ubuntu",),
    )


def _create_spec(template: ResolvedSandboxTemplate):
    from ecosystem.defaultspack.backend.sandbox.models import SandboxCreateSpec

    return SandboxCreateSpec(name="fake desktop", template=template, provider_id="fake-runtime")
