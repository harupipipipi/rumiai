from __future__ import annotations

from collections.abc import Sequence

from ecosystem.defaultspack.backend.sandbox.provider_registry import ProviderRegistry
from ecosystem.defaultspack.backend.sandbox.providers.docker_provider import (
    DockerCommandResult,
    DockerProvider,
)
from ecosystem.defaultspack.backend.sandbox.sandbox_manager import SandboxManager
from ecosystem.defaultspack.domain.coding.workspace_store import WorkspaceStore


class FakeDockerCli:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None, float | None]] = []
        self.states: dict[str, str] = {}
        self.networks: dict[str, str] = {}
        self.exec_stdout = "hello\n"
        self.forwarders: list[FakeDockerPortForwarder] = []

    def __call__(
        self,
        command: Sequence[str],
        input_text: str | None,
        timeout: float | None,
    ) -> DockerCommandResult:
        cmd = list(command)
        self.calls.append((cmd, input_text, timeout))
        if cmd[1:3] == ["info", "--format"]:
            return DockerCommandResult(returncode=0, stdout="25.0.0\n")
        if cmd[1:3] == ["inspect", "--format"]:
            if "IPAddress" in cmd[3]:
                name = cmd[-1]
                return DockerCommandResult(returncode=0, stdout="172.17.0.2\n" if self.networks.get(name) == "bridge" else "\n")
            name = cmd[-1]
            state = self.states.get(name)
            if state is None:
                return DockerCommandResult(returncode=1, stderr="No such object")
            return DockerCommandResult(returncode=0, stdout=f"{state}\n")
        if len(cmd) > 4 and cmd[1] == "run":
            name = cmd[cmd.index("--name") + 1]
            self.states[name] = "running"
            self.networks[name] = cmd[cmd.index("--network") + 1] if "--network" in cmd else "bridge"
            return DockerCommandResult(returncode=0, stdout=f"{name}\n")
        if cmd[1:3] == ["network", "connect"]:
            self.networks[cmd[4]] = cmd[3]
            return DockerCommandResult(returncode=0)
        if cmd[1] == "start":
            self.states[cmd[2]] = "running"
            return DockerCommandResult(returncode=0, stdout=cmd[2])
        if cmd[1] in {"stop", "kill"}:
            self.states[cmd[2]] = "exited"
            return DockerCommandResult(returncode=0)
        if cmd[1:3] == ["rm", "-f"]:
            self.states.pop(cmd[3], None)
            return DockerCommandResult(returncode=0)
        if cmd[1] == "cp":
            return DockerCommandResult(returncode=0)
        if cmd[1] == "exec":
            if cmd[-3:] == ["mkdir", "-p", "/workspace/src"]:
                return DockerCommandResult(returncode=0)
            return DockerCommandResult(returncode=0, stdout=self.exec_stdout)
        return DockerCommandResult(returncode=1, stderr=f"unexpected docker command: {cmd}")

    def command_with(self, docker_subcommand: str) -> list[str]:
        for command, _input_text, _timeout in self.calls:
            if len(command) > 1 and command[1] == docker_subcommand:
                return command
        raise AssertionError(f"docker {docker_subcommand} was not called")


class FakeDockerPortForwarder:
    host = "127.0.0.1"

    def __init__(self, docker_path: str, container_name: str, target_port: int, *, host_port: int) -> None:
        self.docker_path = docker_path
        self.container_name = container_name
        self.target_port = target_port
        self.host_port = host_port
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _manager(tmp_path, fake: FakeDockerCli) -> SandboxManager:
    def forwarder_factory(docker_path: str, container_name: str, target_port: int) -> FakeDockerPortForwarder:
        forwarder = FakeDockerPortForwarder(docker_path, container_name, target_port, host_port=49152 + len(fake.forwarders))
        fake.forwarders.append(forwarder)
        return forwarder

    registry = ProviderRegistry()
    registry.register(DockerProvider(docker_path="/usr/bin/docker", runner=fake, port_forwarder_factory=forwarder_factory))
    return SandboxManager(state_dir=tmp_path, provider_registry=registry)


def _trusted_workspace(tmp_path, monkeypatch, *, trusted: bool = True) -> str:
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CODING_WORKSPACE_STORE_PATH", str(tmp_path / "workspaces.json"))
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "app.py").write_text("print('hello')\n", encoding="utf-8")
    WorkspaceStore().create(root, workspace_id="trusted", trusted=trusted)
    return str(root)


def test_docker_provider_runs_sandbox_exec_inside_container(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)

    created = manager.create(display=False, provider_id="docker", template_id="tool.ephemeral")
    assert created["ok"] is True
    assert created["provider_id"] == "docker"

    result = manager.exec(
        created["sandbox_id"],
        {
            "argv": ["echo", "hello"],
            "cwd": ".",
            "env": {"RUMI_TEST": "1"},
            "timeout_ms": 10_000,
            "client_request_id": "exec-1",
        },
    )

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["stdout"] == "hello\n"
    docker_exec = fake.command_with("exec")
    assert docker_exec[:2] == ["/usr/bin/docker", "exec"]
    assert docker_exec[-2:] == ["echo", "hello"]
    assert "--env" in docker_exec
    assert "RUMI_TEST=1" in docker_exec
    assert "sh" not in docker_exec[-2:]
    assert "-c" not in docker_exec


def test_docker_provider_rejects_exec_cwd_before_container_exec(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)
    created = manager.create(display=False, provider_id="docker", template_id="tool.ephemeral")
    fake.calls.clear()

    result = manager.exec(
        created["sandbox_id"],
        {"argv": ["pwd"], "cwd": "/tmp/outside", "client_request_id": "exec-cwd"},
    )

    assert result["ok"] is False
    assert result["code"] == "INVALID_EXEC_REQUEST"
    assert all(command[1] != "exec" for command, _input_text, _timeout in fake.calls)


def test_docker_provider_auto_resolves_tool_sandbox(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)

    created = manager.create(display=False, provider_id="auto", template_id="tool.ephemeral")

    assert created["ok"] is True
    assert created["provider_id"] == "docker"
    docker_run = fake.command_with("run")
    assert "--network" in docker_run
    assert docker_run[docker_run.index("--network") + 1] == "none"


def test_docker_provider_uses_python_image_for_python_template(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)

    created = manager.create(display=False, provider_id="docker", template_id="coding.python")

    assert created["ok"] is True
    docker_run = fake.command_with("run")
    assert "python:3.11-slim" in docker_run
    assert docker_run[docker_run.index("--network") + 1] == "none"
    assert "--memory" in docker_run
    assert "4096m" in docker_run


def test_docker_provider_uses_node_image_for_node_template(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)

    created = manager.create(display=False, provider_id="docker", template_id="coding.node")

    assert created["ok"] is True
    docker_run = fake.command_with("run")
    assert "node:20-bookworm-slim" in docker_run


def test_docker_provider_mounts_trusted_workspace_read_only(tmp_path, monkeypatch) -> None:
    workspace_root = _trusted_workspace(tmp_path, monkeypatch)
    fake = FakeDockerCli()
    manager = _manager(tmp_path / "state", fake)

    created = manager.create(
        display=False,
        provider_id="docker",
        template_id="coding.python",
        workspace_id="trusted",
        workspace_access="read_only",
    )

    assert created["ok"] is True
    docker_run = fake.command_with("run")
    assert "--mount" in docker_run
    mount = docker_run[docker_run.index("--mount") + 1]
    assert mount == f"type=bind,source={workspace_root},target=/workspace,readonly"


def test_docker_provider_seeds_trusted_workspace_overlay(tmp_path, monkeypatch) -> None:
    workspace_root = _trusted_workspace(tmp_path, monkeypatch)
    fake = FakeDockerCli()
    manager = _manager(tmp_path / "state", fake)

    created = manager.create(
        display=False,
        provider_id="docker",
        template_id="coding.python",
        workspace_id="trusted",
        workspace_access="overlay",
    )

    assert created["ok"] is True
    docker_run = fake.command_with("run")
    docker_cp = fake.command_with("cp")
    assert "--mount" not in docker_run
    assert docker_cp[-2:] == [f"{workspace_root}/.", docker_run[docker_run.index("--name") + 1] + ":/workspace"]


def test_docker_provider_rejects_untrusted_workspace_binding(tmp_path, monkeypatch) -> None:
    _trusted_workspace(tmp_path, monkeypatch, trusted=False)
    fake = FakeDockerCli()
    manager = _manager(tmp_path / "state", fake)

    created = manager.create(
        display=False,
        provider_id="docker",
        template_id="coding.python",
        workspace_id="trusted",
        workspace_access="read_only",
    )

    assert created["ok"] is False
    assert created["code"] == "SANDBOX_WORKSPACE_UNTRUSTED"
    assert fake.calls == []


def test_docker_provider_applies_file_patch_inside_container(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)
    created = manager.create(display=False, provider_id="docker", template_id="coding.python")

    result = manager.apply_file_patch(
        created["sandbox_id"],
        {"files": [{"path": "src/app.py", "content": "print('hello')\n"}]},
    )

    assert result["ok"] is True
    assert result["files_written"] == 1
    mkdir = fake.command_with("exec")
    copy = fake.command_with("cp")
    assert mkdir[-3:] == ["mkdir", "-p", "/workspace/src"]
    assert copy[-1].endswith(":/workspace/src/app.py")


def test_docker_provider_rejects_file_patch_path_traversal(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)
    created = manager.create(display=False, provider_id="docker", template_id="coding.python")

    result = manager.apply_file_patch(
        created["sandbox_id"],
        {"path": "../outside.py", "content": "print('outside')"},
    )

    assert result["ok"] is False
    assert result["code"] == "INVALID_EXEC_REQUEST"


def test_docker_provider_exposes_container_port_metadata(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)
    created = manager.create(display=False, provider_id="docker", template_id="coding.python")

    denied = manager.expose_port(created["sandbox_id"], {"port": 3000, "protocol": "http"})
    result = manager.expose_port(created["sandbox_id"], {"port": 3000, "protocol": "http"}, approved=True)
    repeated = manager.expose_port(created["sandbox_id"], {"port": 3000, "protocol": "http"}, approved=True)
    destroyed = manager.destroy(created["sandbox_id"])

    assert denied["ok"] is False
    assert denied["code"] == "SANDBOX_NETWORK_REQUIRES_APPROVAL"
    assert result["ok"] is True
    assert result["port"] == 3000
    assert result["url"] == "http://127.0.0.1:49152"
    assert result["target_url"] == "http://127.0.0.1:3000"
    assert result["container_url"] == "http://127.0.0.1:3000"
    assert result["host_reachable"] is True
    assert result["forwarding"] == "docker_exec_proxy"
    assert repeated["url"] == result["url"]
    network_connect = [call for call, _input, _timeout in fake.calls if call[1:4] == ["network", "connect", "bridge"]]
    assert network_connect == []
    assert fake.networks[f"rumi-sandbox-{created['sandbox_id']}"] == "none"
    assert len(fake.forwarders) == 1
    assert fake.forwarders[0].docker_path == "/usr/bin/docker"
    assert fake.forwarders[0].container_name == f"rumi-sandbox-{created['sandbox_id']}"
    assert fake.forwarders[0].target_port == 3000
    assert destroyed["ok"] is True
    assert fake.forwarders[0].stopped is True


def test_docker_port_forward_grant_expires_on_stop_restart(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)
    created = manager.create(display=False, provider_id="docker", template_id="coding.python")

    first = manager.expose_port(created["sandbox_id"], {"port": 3000, "protocol": "http"}, approved=True)
    stopped = manager.stop(created["sandbox_id"])
    restarted = manager.start(created["sandbox_id"])
    second = manager.expose_port(created["sandbox_id"], {"port": 3000, "protocol": "http"}, approved=True)

    assert first["ok"] is True
    assert stopped["ok"] is True
    assert restarted["ok"] is True
    assert fake.forwarders[0].stopped is True
    assert second["ok"] is True
    assert second["url"] == "http://127.0.0.1:49153"
    assert len(fake.forwarders) == 2
    network_connect = [call for call, _input, _timeout in fake.calls if call[1:4] == ["network", "connect", "bridge"]]
    assert network_connect == []
    assert fake.networks[f"rumi-sandbox-{created['sandbox_id']}"] == "none"
