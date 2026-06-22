from __future__ import annotations

import base64
from collections.abc import Sequence

import pytest

from ecosystem.defaultspack.backend.sandbox.models import (
    DesktopSpec,
    EnsureRuntimeRequest,
    FilesystemPolicy,
    LifecyclePolicy,
    NetworkPolicy,
    PackageSpec,
    ResolvedSandboxTemplate,
    ResourceLimits,
    RuntimeRequirements,
    SandboxCreateSpec,
    SecretsPolicy,
    WorkspaceBinding,
)
from ecosystem.defaultspack.backend.sandbox.errors import SandboxContractError
from ecosystem.defaultspack.backend.sandbox.provider_registry import ProviderRegistry
from ecosystem.defaultspack.backend.sandbox.providers.base import NullProgressSink
from ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu import (
    DEFAULT_WSL_RUNTIME_NAME,
    GuestCommandResult,
    MANAGED_UBUNTU_CAPABILITIES,
    MacLimaProvider,
    WSL_ROOTFS_ENV,
    WindowsWslProvider,
)


class FakeManagedUbuntuCli:
    def __init__(self, *, mode: str, runtime_name: str) -> None:
        self.mode = mode
        self.runtime_name = runtime_name
        self.calls: list[tuple[list[str], str | None, float | None]] = []
        self.guest_scripts: list[str] = []
        self.guest_exists = False
        self.deps_installed = False
        self.desktop_running = False
        self.imported_rootfs_path: str | None = None
        self.imported_install_dir: str | None = None

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
        if len(cmd) >= 7 and cmd[1:3] == ["--import", self.runtime_name]:
            self.guest_exists = True
            self.imported_install_dir = cmd[3]
            self.imported_rootfs_path = cmd[4]
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
        if argv[:5] == ["unshare", "--user", "--map-root-user", "--net", "--"]:
            return self._guest(argv[5:], input_text)
        if argv[:2] == ["bash", "-lc"]:
            script = argv[2]
            self.guest_scripts.append(script)
            if "rumi-resource-limit" in argv and "ulimit -v" in script and "ulimit -u" in script:
                marker_index = argv.index("rumi-resource-limit")
                return self._guest(argv[marker_index + 4 :], input_text)
            if "PROVISION_MARKER" in script:
                return GuestCommandResult(returncode=0)
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
        if argv[:1] == ["emit-long"]:
            return GuestCommandResult(returncode=0, stdout="0123456789", stderr="abcdefghij")
        if argv[:2] == ["echo", "hello"]:
            return GuestCommandResult(returncode=0, stdout="hello\n")
        return GuestCommandResult(returncode=0)


def _template(
    *,
    desktop: bool = True,
    output_bytes: int = 4096,
    timeout_ms: int | None = None,
    memory_mb: int = 2048,
    cpu_count: float | None = 1,
    pids: int | None = None,
    network_mode: str = "limited_or_approval_gated",
    network_approval_required: bool = True,
    packages: tuple[PackageSpec, ...] = (),
) -> ResolvedSandboxTemplate:
    return ResolvedSandboxTemplate(
        template_id="desktop.ubuntu" if desktop else "coding.python",
        template_version="1",
        runtime_os="linux",
        provider_requirements=MANAGED_UBUNTU_CAPABILITIES if desktop else frozenset({"sandbox.exec", "sandbox.files", "sandbox.port_forward"}),
        packages=packages,
        desktop=DesktopSpec(enabled=True, width=800, height=600) if desktop else None,
        filesystem=FilesystemPolicy(),
        network=NetworkPolicy(mode=network_mode, approval_required=network_approval_required),
        secrets=SecretsPolicy(),
        resources=ResourceLimits(memory_mb=memory_mb, cpu_count=cpu_count, pids=pids, output_bytes=output_bytes, timeout_ms=timeout_ms),
        lifecycle=LifecyclePolicy(),
        allowed_operations=MANAGED_UBUNTU_CAPABILITIES,
        source_template_ids=("test",),
    )


def _create_spec(
    template: ResolvedSandboxTemplate,
    *,
    startup: dict[str, object] | None = None,
    provisioning: dict[str, object] | None = None,
) -> SandboxCreateSpec:
    return SandboxCreateSpec(
        name="Managed Ubuntu",
        template=template,
        provider_id="auto",
        workspace_binding=WorkspaceBinding(workspace_id="workspace-1", mode="read_only"),
        metadata={
            "startup": startup or {"starter": "terminal"},
            "desktop_provisioning": provisioning or {},
        },
    )


def test_mac_lima_provider_ensure_and_guest_desktop_flow(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Darwin")
    fake = FakeManagedUbuntuCli(mode="lima", runtime_name="rumi-managed-runtime")
    provider = MacLimaProvider(command_path="/usr/bin/limactl", runner=fake)
    requirements = RuntimeRequirements(required_capabilities=MANAGED_UBUNTU_CAPABILITIES)

    before = provider.doctor(requirements)
    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="mac_lima", requirements=requirements), NullProgressSink())
    after = provider.doctor(requirements)
    instance = provider.create(_create_spec(_template(network_mode="host_shared", network_approval_required=False)))
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
    assert any("xterm -title 'Rumi Desktop'" in script for script in fake.guest_scripts)
    assert fake.command_containing("shell", "rumi-managed-runtime", "--", "echo", "hello")[-2:] == ["echo", "hello"]


def test_windows_wsl_provider_ensure_imports_rumi_owned_distribution(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Windows")
    rootfs = tmp_path / "rumi-ubuntu-rootfs.tar"
    rootfs.write_bytes(b"rootfs")
    install_dir = tmp_path / "RumiUbuntu"
    fake = FakeManagedUbuntuCli(mode="wsl", runtime_name=DEFAULT_WSL_RUNTIME_NAME)
    provider = WindowsWslProvider(
        command_path="C:/Windows/System32/wsl.exe",
        runner=fake,
        rootfs_path=str(rootfs),
        install_dir=str(install_dir),
    )
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
    assert fake.imported_rootfs_path == str(rootfs)
    assert fake.imported_install_dir == str(install_dir)
    assert executed["stdout"] == "hello\n"
    assert fake.command_containing("--import", DEFAULT_WSL_RUNTIME_NAME, str(install_dir), str(rootfs), "--version", "2")
    assert fake.command_containing("-d", DEFAULT_WSL_RUNTIME_NAME, "--", "echo", "hello")[-2:] == ["echo", "hello"]


def test_windows_wsl_provider_does_not_claim_existing_user_ubuntu_distribution(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Windows")
    fake = FakeManagedUbuntuCli(mode="wsl", runtime_name="Ubuntu")
    fake.guest_exists = True
    provider = WindowsWslProvider(command_path="C:/Windows/System32/wsl.exe", runner=fake)

    status = provider.doctor(RuntimeRequirements(required_capabilities=frozenset({"sandbox.exec"})))

    assert status.ready is False
    assert "managed_guest" in status.missing_requirements


def test_windows_wsl_provider_fails_closed_without_rumi_rootfs(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Windows")
    monkeypatch.delenv(WSL_ROOTFS_ENV, raising=False)
    fake = FakeManagedUbuntuCli(mode="wsl", runtime_name=DEFAULT_WSL_RUNTIME_NAME)
    provider = WindowsWslProvider(command_path="C:/Windows/System32/wsl.exe", runner=fake)

    ensured = provider.ensure(
        EnsureRuntimeRequest(
            provider_id="windows_wsl",
            requirements=RuntimeRequirements(required_capabilities=frozenset({"sandbox.exec"})),
        ),
        NullProgressSink(),
    )

    assert ensured.ok is False
    assert [diagnostic.code for diagnostic in ensured.diagnostics] == ["RUNTIME_PROVIDER_UNAVAILABLE"]
    assert fake.guest_exists is False


def test_managed_ubuntu_exec_enforces_template_output_and_timeout_limits(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Darwin")
    fake = FakeManagedUbuntuCli(mode="lima", runtime_name="rumi-managed-runtime")
    provider = MacLimaProvider(command_path="/usr/bin/limactl", runner=fake)
    requirements = RuntimeRequirements(required_capabilities=frozenset({"sandbox.exec", "sandbox.files"}))

    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="mac_lima", requirements=requirements), NullProgressSink())
    instance = provider.create(_create_spec(_template(desktop=False, output_bytes=5, timeout_ms=2_000, memory_mb=64, cpu_count=2, pids=32)))
    started = provider.start(instance)
    agent = provider.connect_agent(started)
    executed = agent.exec(started.sandbox_id, {"argv": ["emit-long"], "cwd": ".", "client_request_id": "exec-long", "timeout_ms": 600_000})
    exec_call = next(call for call in fake.calls if "emit-long" in call[0])

    assert ensured.ok is True
    assert executed["stdout"] == "01234"
    assert executed["stderr"] == "abcde"
    assert executed["stdout_truncated"] is True
    assert executed["stderr_truncated"] is True
    assert exec_call[2] == 2
    assert "unshare" in exec_call[0]
    assert any("ulimit -v" in part for part in exec_call[0])
    assert any("ulimit -u" in part for part in exec_call[0])
    assert any("taskset -c" in part for part in exec_call[0])
    assert "65536" in exec_call[0]
    assert "0-1" in exec_call[0]
    assert "32" in exec_call[0]
    assert exec_call[0][-1] == "emit-long"


def test_managed_ubuntu_desktop_browser_url_starter_is_projected_to_guest(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Darwin")
    fake = FakeManagedUbuntuCli(mode="lima", runtime_name="rumi-managed-runtime")
    provider = MacLimaProvider(command_path="/usr/bin/limactl", runner=fake)
    requirements = RuntimeRequirements(required_capabilities=MANAGED_UBUNTU_CAPABILITIES)

    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="mac_lima", requirements=requirements), NullProgressSink())
    instance = provider.create(
        _create_spec(
            _template(network_mode="host_shared", network_approval_required=False),
            startup={"starter": "browser_url", "browser_url": "https://example.com"},
        )
    )
    started = provider.start(instance)
    start_script = next(script for script in fake.guest_scripts if "BROWSER_URL=" in script)

    assert ensured.ok is True
    assert started.state == "ready"
    assert "BROWSER_URL=https://example.com" in start_script
    assert "google-chrome-stable google-chrome chromium chromium-browser firefox xdg-open" in start_script
    assert "starter-browser.log" in start_script


def test_managed_ubuntu_browser_url_starter_respects_network_policy(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Darwin")
    fake = FakeManagedUbuntuCli(mode="lima", runtime_name="rumi-managed-runtime")
    provider = MacLimaProvider(command_path="/usr/bin/limactl", runner=fake)
    requirements = RuntimeRequirements(required_capabilities=MANAGED_UBUNTU_CAPABILITIES)

    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="mac_lima", requirements=requirements), NullProgressSink())
    instance = provider.create(_create_spec(_template(), startup={"starter": "browser_url", "browser_url": "https://example.com"}))
    started = provider.start(instance)
    start_script = next(script for script in fake.guest_scripts if "starter-browser.log" in script)

    assert ensured.ok is True
    assert started.state == "ready"
    assert "RUMI_NETWORK_DISABLED='1'" in start_script
    assert "browser_url starter skipped by sandbox network policy" in start_script
    assert "google-chrome-stable google-chrome chromium chromium-browser firefox xdg-open" not in start_script


def test_managed_ubuntu_port_exposure_respects_network_policy(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Darwin")
    fake = FakeManagedUbuntuCli(mode="lima", runtime_name="rumi-managed-runtime")
    provider = MacLimaProvider(command_path="/usr/bin/limactl", runner=fake)
    requirements = RuntimeRequirements(required_capabilities=MANAGED_UBUNTU_CAPABILITIES)

    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="mac_lima", requirements=requirements), NullProgressSink())
    instance = provider.create(_create_spec(_template()))
    started = provider.start(instance)
    agent = provider.connect_agent(started)

    assert ensured.ok is True
    with pytest.raises(SandboxContractError) as excinfo:
        agent.expose_port(started.sandbox_id, {"port": 3000, "protocol": "http"})
    assert getattr(excinfo.value, "code", "") == "SANDBOX_NETWORK_DENIED"


def test_managed_ubuntu_desktop_provisioning_installs_declared_apps_and_mcp(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Darwin")
    fake = FakeManagedUbuntuCli(mode="lima", runtime_name="rumi-managed-runtime")
    provider = MacLimaProvider(command_path="/usr/bin/limactl", runner=fake)
    requirements = RuntimeRequirements(required_capabilities=MANAGED_UBUNTU_CAPABILITIES)
    provisioning = {
        "packages": [{"name": "google-chrome-stable"}, {"name": "python"}],
        "apps": ["xterm", "code-editor"],
        "mcp_servers": ["playwright"],
    }

    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="mac_lima", requirements=requirements), NullProgressSink())
    instance = provider.create(_create_spec(_template(), provisioning=provisioning))
    started = provider.start(instance)
    provision_script = next(script for script in fake.guest_scripts if "PROVISION_MARKER" in script)

    assert ensured.ok is True
    assert started.state == "ready"
    assert "google-chrome-stable" in provision_script
    assert "python3" in provision_script
    assert "python3-pip" in provision_script
    assert "xterm" in provision_script
    assert "code-editor" not in provision_script
    assert "/workspace/.rumi/mcp_servers.txt" in provision_script
    assert "@playwright/mcp" in provision_script


def test_managed_ubuntu_template_packages_are_guest_provisioned(monkeypatch) -> None:
    monkeypatch.setattr("ecosystem.defaultspack.backend.sandbox.providers.managed_ubuntu.platform.system", lambda: "Darwin")
    fake = FakeManagedUbuntuCli(mode="lima", runtime_name="rumi-managed-runtime")
    provider = MacLimaProvider(command_path="/usr/bin/limactl", runner=fake)
    requirements = RuntimeRequirements(required_capabilities=MANAGED_UBUNTU_CAPABILITIES)
    template = _template(
        packages=(
            PackageSpec(name="node", version="20+", source="guest"),
            PackageSpec(name="python", version="3.11+", source="guest"),
            PackageSpec(name="not-a-known-app", source="guest"),
        )
    )

    ensured = provider.ensure(EnsureRuntimeRequest(provider_id="mac_lima", requirements=requirements), NullProgressSink())
    instance = provider.create(_create_spec(template))
    started = provider.start(instance)
    provision_script = next(script for script in fake.guest_scripts if "PROVISION_MARKER" in script)

    assert ensured.ok is True
    assert started.state == "ready"
    assert "nodejs" in provision_script
    assert "npm" in provision_script
    assert "python3" in provision_script
    assert "python3-pip" in provision_script
    assert "not-a-known-app" not in provision_script


def test_default_sandbox_api_registers_cross_platform_runtime_providers() -> None:
    from ecosystem.defaultspack.blocks.sandbox import api

    service = api._SandboxApiService()
    provider_ids = set(service.provider_registry.provider_ids())

    assert {"linux_native", "mac_lima", "windows_wsl", "docker"} <= provider_ids
    api._reset_service_for_tests(None)
