from __future__ import annotations

import base64
from collections.abc import Sequence

from ecosystem.defaultspack.backend.sandbox.models import (
    DesktopSpec,
    EnsureRuntimeRequest,
    FilesystemPolicy,
    LifecyclePolicy,
    NetworkPolicy,
    ResolvedSandboxTemplate,
    ResourceLimits,
    RuntimeRequirements,
    SandboxCreateSpec,
    SecretsPolicy,
    WorkspaceBinding,
)
from ecosystem.defaultspack.backend.sandbox.provider_registry import ProviderRegistry
from ecosystem.defaultspack.backend.sandbox.providers.base import NullProgressSink
from ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu import (
    GuestCommandResult,
    MANAGED_UBUNTU_CAPABILITIES,
    MacLimaProvider,
    WindowsWslProvider,
)


class FakeManagedUbuntuCli:
    def __init__(self, *, mode: str, runtime_name: str) -> None:
        self.mode = mode
        self.runtime_name = runtime_name
        self.calls: list[tuple[list[str], str | None, float | None]] = []
        self.guest_exists = False
        self.deps_installed = False
        self.desktop_running = False

    def __call__(
        self,
        command: Sequence[str],
        input_text: str | None,
        timeout: float | None,
    ) -> GuestCommandResult:
        cmd = list(command)
        self.calls.append((cmd, input_text, timeout))
        if self.mode == "lima":
            return self._lima(cmd, input_text)
        return self._wsl(cmd, input_text)

    def command_containing(self, *parts: str) -> list[str]:
        for command, _input_text, _timeout in self.calls:
            if all(part in command for part in parts):
                return command
        raise AssertionError(f"command containing {parts!r} was not called")

    def _lima(self, cmd: list[str], input_text: str | None) -> GuestCommandResult:
        if cmd[1:] == ["--version"]:
            return GuestCommandResult(returncode=0, stdout="limactl version 1.0\n")
        if cmd[1:3] == ["list", "--format"]:
            return GuestCommandResult(returncode=0, stdout=f"{self.runtime_name}\n" if self.guest_exists else "")
        if cmd[1:4] == ["start", "--name", self.runtime_name]:
            self.guest_exists = True
            self.deps_installed = True
            return GuestCommandResult(returncode=0)
        if cmd[1:3] == ["start", self.runtime_name]:
            return GuestCommandResult(returncode=0)
        if cmd[1:3] == ["stop", "--force"]:
            return GuestCommandResult(returncode=0)
        if cmd[1:3] == ["delete", "--force"]:
            self.guest_exists = False
            self.deps_installed = False
            return GuestCommandResult(returncode=0)
        if cmd[1:4] == ["shell", self.runtime_name, "--"]:
            return self._guest(cmd[4:], input_text)
        return GuestCommandResult(returncode=1, stderr=f"unexpected lima command: {cmd}")

    def _wsl(self, cmd: list[str], input_text: str | None) -> GuestCommandResult:
        if cmd[1:] == ["--version"]:
            return GuestCommandResult(returncode=0, stdout="WSL version: 2.0\n")
        if cmd[1:] == ["-l", "-q"]:
            return GuestCommandResult(returncode=0, stdout=f"{self.runtime_name}\n" if self.guest_exists else "")
        if cmd[1:4] == ["--install", "-d", self.runtime_name]:
            self.guest_exists = True
            return GuestCommandResult(returncode=0)
        if cmd[1:3] == ["--terminate", self.runtime_name]:
            return GuestCommandResult(returncode=0)
        if cmd[1:3] == ["--unregister", self.runtime_name]:
            self.guest_exists = False
            self.deps_installed = False
            return GuestCommandResult(returncode=0)
        if cmd[1:4] == ["-d", self.runtime_name, "--"]:
            return self._guest(cmd[4:], input_text)
        return GuestCommandResult(returncode=1, stderr=f"unexpected wsl command: {cmd}")

    def _guest(self, argv: list[str], input_text: str | None) -> GuestCommandResult:
        if argv[:2] == ["bash", "-lc"]:
            script = argv[2]
            if "command -v" in script:
                if self.deps_installed:
                    return GuestCommandResult(returncode=0)
                return GuestCommandResult(returncode=0, stdout="Xvfb\nopenbox\nxdotool\nimport\npython3\n")
            if "apt-get install" in script:
                self.deps_installed = True
                return GuestCommandResult(returncode=0)
            if "Xvfb" in script and "openbox" in script:
                self.desktop_running = True
                return GuestCommandResult(returncode=0)
            if "kill -0" in script:
                return GuestCommandResult(returncode=0 if self.desktop_running else 1)
            return GuestCommandResult(returncode=0)
        if argv[:2] == ["mkdir", "-p"]:
            return GuestCommandResult(returncode=0)
        if argv[:2] == ["python3", "-c"]:
            assert input_text
            return GuestCommandResult(returncode=0)
        if argv[:3] == ["env", "DISPLAY=:98", "bash"]:
            return GuestCommandResult(returncode=0, stdout=base64.b64encode(b"png").decode("ascii"))
        if argv[:3] == ["env", "DISPLAY=:98", "xdotool"]:
            return GuestCommandResult(returncode=0)
        if argv[:2] == ["echo", "hello"]:
            return GuestCommandResult(returncode=0, stdout="hello\n")
        return GuestCommandResult(returncode=0)


def _template(*, desktop: bool = True) -> ResolvedSandboxTemplate:
    return ResolvedSandboxTemplate(
        template_id="desktop.ubuntu" if desktop else "coding.python",
        template_version="1",
        runtime_os="linux",
        provider_requirements=MANAGED_UBUNTU_CAPABILITIES if desktop else frozenset({"sandbox.exec", "sandbox.files", "sandbox.port_forward"}),
        packages=(),
        desktop=DesktopSpec(enabled=True, width=800, height=600) if desktop else None,
        filesystem=FilesystemPolicy(),
        network=NetworkPolicy(mode="limited_or_approval_gated"),
        secrets=SecretsPolicy(),
        resources=ResourceLimits(memory_mb=2048, cpu_count=1, output_bytes=4096),
        lifecycle=LifecyclePolicy(),
        allowed_operations=MANAGED_UBUNTU_CAPABILITIES,
        source_template_ids=("test",),
    )


def _create_spec(template: ResolvedSandboxTemplate) -> SandboxCreateSpec:
    return SandboxCreateSpec(
        name="Managed Ubuntu",
        template=template,
        provider_id="auto",
        workspace_binding=WorkspaceBinding(workspace_id="workspace-1", mode="read_only"),
        metadata={"startup": {"starter": "terminal"}},
    )


def test_mac_lima_provider_ensure_and_guest_desktop_flow(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Darwin")
    fake = FakeManagedUbuntuCli(mode="lima", runtime_name="rumi-managed-runtime")
    provider = MacLimaProvider(command_path="/usr/bin/limactl", runner=fake)
    requirements = RuntimeRequirements(required_capabilities=MANAGED_UBUNTU_CAPABILITIES)

    before = provider.doctor(requirements)
    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="mac_lima", requirements=requirements), NullProgressSink())
    after = provider.doctor(requirements)
    instance = provider.create(_create_spec(_template()))
    started = provider.start(instance)
    agent = provider.connect_agent(started)
    executed = agent.exec(started.sandbox_id, {"argv": ["echo", "hello"], "cwd": ".", "client_request_id": "exec-1"})
    patched = agent.apply_file_patch(started.sandbox_id, {"path": "src/app.py", "content": "print('hello')\n"})
    exposed = agent.expose_port(started.sandbox_id, {"port": 3000, "protocol": "http"})
    frame = agent.capture_frame(started.sandbox_id, started.sandbox_id)
    click = agent.desktop_input(started.sandbox_id, started.sandbox_id, {"action": "click", "client_action_id": "click-1", "x": 1, "y": 2})

    assert before.ready is False
    assert "managed_guest" in before.missing_requirements
    assert ensured.ok is True
    assert after.ready is True
    assert started.state == "ready"
    assert executed["stdout"] == "hello\n"
    assert patched["ok"] is True
    assert exposed["target_url"] == "http://127.0.0.1:3000"
    assert frame["data"] == b"png"
    assert click["ok"] is True
    assert fake.command_containing("shell", "rumi-managed-runtime", "--", "echo", "hello")[-2:] == ["echo", "hello"]


def test_windows_wsl_provider_ensure_installs_distribution(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Windows")
    fake = FakeManagedUbuntuCli(mode="wsl", runtime_name="Ubuntu")
    provider = WindowsWslProvider(command_path="C:/Windows/System32/wsl.exe", runner=fake)
    requirements = RuntimeRequirements(required_capabilities=frozenset({"sandbox.exec", "sandbox.files"}))

    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="windows_wsl", requirements=requirements), NullProgressSink())
    status = provider.doctor(requirements)
    instance = provider.create(_create_spec(_template(desktop=False)))
    started = provider.start(instance)
    agent = provider.connect_agent(started)
    executed = agent.exec(started.sandbox_id, {"argv": ["echo", "hello"], "cwd": ".", "client_request_id": "exec-1"})

    assert ensured.ok is True
    assert status.ready is True
    assert fake.guest_exists is True
    assert fake.deps_installed is True
    assert executed["stdout"] == "hello\n"
    assert fake.command_containing("-d", "Ubuntu", "--", "echo", "hello")[-2:] == ["echo", "hello"]


def test_default_sandbox_api_registers_cross_platform_runtime_providers() -> None:
    from ecosystem.defaultspack.blocks.sandbox import api

    service = api._SandboxApiService()
    provider_ids = set(service.provider_registry.provider_ids())

    assert {"linux_native", "mac_lima", "windows_wsl", "docker"} <= provider_ids
    api._reset_service_for_tests(None)
