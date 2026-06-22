from __future__ import annotations

from collections.abc import Sequence

from ecosystem.defaultspack.backend.sandbox.provider_registry import ProviderRegistry
from ecosystem.defaultspack.backend.sandbox.providers.docker_provider import (
    DockerCommandResult,
    DockerProvider,
)
from ecosystem.defaultspack.backend.sandbox.sandbox_manager import SandboxManager


class FakeDockerCli:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None, float | None]] = []
        self.states: dict[str, str] = {}
        self.exec_stdout = "hello\n"

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
                return DockerCommandResult(returncode=0, stdout="172.17.0.2\n")
            name = cmd[-1]
            state = self.states.get(name)
            if state is None:
                return DockerCommandResult(returncode=1, stderr="No such object")
            return DockerCommandResult(returncode=0, stdout=f"{state}\n")
        if len(cmd) > 4 and cmd[1] == "run":
            name = cmd[cmd.index("--name") + 1]
            self.states[name] = "running"
            return DockerCommandResult(returncode=0, stdout=f"{name}\n")
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


def _manager(tmp_path, fake: FakeDockerCli) -> SandboxManager:
    registry = ProviderRegistry()
    registry.register(DockerProvider(docker_path="/usr/bin/docker", runner=fake))
    return SandboxManager(state_dir=tmp_path, provider_registry=registry)


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
    assert docker_run[docker_run.index("--network") + 1] == "bridge"
    assert "--memory" in docker_run
    assert "4096m" in docker_run


def test_docker_provider_uses_node_image_for_node_template(tmp_path) -> None:
    fake = FakeDockerCli()
    manager = _manager(tmp_path, fake)

    created = manager.create(display=False, provider_id="docker", template_id="coding.node")

    assert created["ok"] is True
    docker_run = fake.command_with("run")
    assert "node:20-bookworm-slim" in docker_run


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

    result = manager.expose_port(created["sandbox_id"], {"port": 3000, "protocol": "http"})

    assert result["ok"] is True
    assert result["port"] == 3000
    assert result["target_url"] == "http://172.17.0.2:3000"
