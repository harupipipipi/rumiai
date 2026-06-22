from __future__ import annotations

import platform
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable, Mapping, Sequence

from ..errors import RUNTIME_PROVIDER_UNAVAILABLE, SandboxContractError
from ..guest.protocol import GuestExecRequest
from ..models import (
    Diagnostic,
    EnsureRuntimeRequest,
    OperationResult,
    ProgressEvent,
    ProviderInstance,
    ReconcileResult,
    RuntimeProviderStatus,
    RuntimeRequirements,
    SandboxCreateSpec,
    UninstallRuntimeRequest,
    UpdateRuntimeRequest,
)
from .base import ProgressSink


DOCKER_CAPABILITIES = frozenset(
    {
        "sandbox.exec",
        "sandbox.files",
        "sandbox.overlay_workspace",
        "sandbox.port_forward",
        "sandbox.network_policy",
        "sandbox.resource_limits",
        "sandbox.container",
    }
)
DEFAULT_DOCKER_IMAGE = "ubuntu:22.04"
CODING_PYTHON_IMAGE = "python:3.11-slim"
CODING_NODE_IMAGE = "node:20-bookworm-slim"
CONTAINER_WORKDIR = "/workspace"


@dataclass(frozen=True)
class DockerCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


DockerRunner = Callable[[Sequence[str], str | None, float | None], DockerCommandResult]


class DockerProvider:
    """Optional container runtime provider for non-desktop sandbox execution."""

    provider_id = "docker"

    def __init__(
        self,
        *,
        docker_path: str | None = None,
        runner: DockerRunner | None = None,
    ) -> None:
        self._configured_docker_path = docker_path
        self._runner = runner or _subprocess_runner
        self._instances: dict[str, ProviderInstance] = {}

    def doctor(self, request: RuntimeRequirements) -> RuntimeProviderStatus:
        docker_path = self._docker_path()
        diagnostics: list[Diagnostic] = []
        missing: list[str] = []
        version: str | None = None
        installed = False

        if docker_path is None:
            missing.append("command:docker")
            diagnostics.append(
                Diagnostic(
                    code="DOCKER_COMMAND_MISSING",
                    message="Docker CLI was not found on PATH.",
                    severity="info",
                )
            )
        else:
            result = self._run([docker_path, "info", "--format", "{{.ServerVersion}}"], timeout=5)
            installed = result.returncode == 0
            version = result.stdout.strip() or None
            if not installed:
                missing.append("docker_daemon")
                diagnostics.append(
                    Diagnostic(
                        code="DOCKER_DAEMON_UNAVAILABLE",
                        message="Docker CLI is present, but the Docker daemon is not reachable.",
                        severity="warning",
                        details={"stderr": result.stderr.strip()[:500]},
                    )
                )

        missing_capabilities = sorted(request.required_capabilities - DOCKER_CAPABILITIES)
        missing.extend(missing_capabilities)
        ready = docker_path is not None and installed and not missing_capabilities
        return RuntimeProviderStatus(
            provider_id=self.provider_id,
            platform=platform.system().lower() or "unknown",
            available=docker_path is not None,
            installed=installed,
            ready=ready,
            version=version,
            capabilities=DOCKER_CAPABILITIES if docker_path is not None else frozenset(),
            missing_requirements=tuple(missing),
            requires_user_action=not ready,
            user_action=None if ready else "Start Docker or choose a managed platform provider.",
            diagnostics=tuple(diagnostics),
        )

    def ensure(self, request: EnsureRuntimeRequest, progress: ProgressSink) -> OperationResult:
        progress.emit(ProgressEvent(operation_id="docker-ensure", stage="doctor", message="Checking Docker runtime"))
        status = self.doctor(request.requirements)
        if status.ready:
            progress.emit(ProgressEvent(operation_id="docker-ensure", stage="ready", message="Docker runtime is ready", percent=100))
            return OperationResult(ok=True, provider_id=self.provider_id, operation_id="docker-ensure", status="completed")
        return OperationResult(
            ok=False,
            provider_id=self.provider_id,
            operation_id="docker-ensure",
            status="failed",
            diagnostics=status.diagnostics,
            requires_user_action=status.requires_user_action,
            user_action=status.user_action,
        )

    def update(self, request: UpdateRuntimeRequest, progress: ProgressSink) -> OperationResult:
        del request
        progress.emit(ProgressEvent(operation_id="docker-update", stage="skipped", message="Docker is managed outside Rumi", percent=100))
        return OperationResult(ok=True, provider_id=self.provider_id, operation_id="docker-update", status="skipped")

    def uninstall(self, request: UninstallRuntimeRequest, progress: ProgressSink) -> OperationResult:
        del request
        for instance in list(self._instances.values()):
            self.destroy(instance)
        progress.emit(ProgressEvent(operation_id="docker-uninstall", stage="stopped", message="Stopped Docker sandbox containers", percent=100))
        return OperationResult(ok=True, provider_id=self.provider_id, operation_id="docker-uninstall", status="completed")

    def create(self, spec: SandboxCreateSpec) -> ProviderInstance:
        if spec.template.desktop is not None and spec.template.desktop.enabled:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                "Docker provider currently supports non-desktop sandbox templates only.",
                status_code=503,
            )
        docker_path = self._require_docker_ready(spec.template.provider_requirements)
        sandbox_id = str(uuid.uuid4())
        image = _image_for_spec(spec)
        name = _container_name(sandbox_id)
        instance = ProviderInstance(
            provider_id=self.provider_id,
            provider_instance_id=name,
            sandbox_id=sandbox_id,
            runtime_id="docker",
            state="stopped",
            opaque_state={
                "docker_path": docker_path,
                "container_name": name,
                "image": image,
                "network_mode": _docker_network_mode(spec),
                "memory_mb": spec.template.resources.memory_mb,
                "cpu_count": spec.template.resources.cpu_count,
                "pids": spec.template.resources.pids,
                "output_bytes": spec.template.resources.output_bytes,
                "template_id": spec.template.template_id,
            },
        )
        self._instances[instance.provider_instance_id] = instance
        return instance

    def start(self, instance: ProviderInstance) -> ProviderInstance:
        docker_path = str(instance.opaque_state.get("docker_path") or self._require_docker_ready(frozenset({"sandbox.exec"})))
        name = str(instance.opaque_state.get("container_name") or instance.provider_instance_id)
        state = self._inspect_state(docker_path, name)
        if state == "running":
            return self._started(instance)
        if state in {"created", "exited", "paused"}:
            result = self._run([docker_path, "start", name], timeout=30)
            if result.returncode != 0:
                raise _docker_error("DOCKER_START_FAILED", "Docker sandbox container did not start.", result, status_code=503)
            return self._started(instance)

        command = _docker_run_command(docker_path, name, instance.opaque_state)
        result = self._run(command, timeout=120)
        if result.returncode != 0:
            raise _docker_error("DOCKER_START_FAILED", "Docker sandbox container did not start.", result, status_code=503)
        return self._started(instance)

    def stop(self, instance: ProviderInstance, *, force: bool = False) -> None:
        docker_path = str(instance.opaque_state.get("docker_path") or self._docker_path() or "docker")
        name = str(instance.opaque_state.get("container_name") or instance.provider_instance_id)
        command = [docker_path, "kill", name] if force else [docker_path, "stop", name]
        self._run(command, timeout=30)
        self._instances[instance.provider_instance_id] = ProviderInstance(
            provider_id=instance.provider_id,
            provider_instance_id=instance.provider_instance_id,
            sandbox_id=instance.sandbox_id,
            runtime_id=instance.runtime_id,
            state="stopped",
            opaque_state=instance.opaque_state,
            generation=instance.generation + 1,
        )

    def destroy(self, instance: ProviderInstance) -> None:
        docker_path = str(instance.opaque_state.get("docker_path") or self._docker_path() or "docker")
        name = str(instance.opaque_state.get("container_name") or instance.provider_instance_id)
        self._run([docker_path, "rm", "-f", name], timeout=30)
        self._instances.pop(instance.provider_instance_id, None)

    def reconcile(self, persisted: ProviderInstance) -> ReconcileResult:
        docker_path = str(persisted.opaque_state.get("docker_path") or self._docker_path() or "docker")
        name = str(persisted.opaque_state.get("container_name") or persisted.provider_instance_id)
        state = self._inspect_state(docker_path, name)
        reconciled_state = "ready" if state == "running" else "stopped"
        current = ProviderInstance(
            provider_id=persisted.provider_id,
            provider_instance_id=persisted.provider_instance_id,
            sandbox_id=persisted.sandbox_id,
            runtime_id=persisted.runtime_id,
            state=reconciled_state,
            opaque_state=persisted.opaque_state,
            generation=persisted.generation,
        )
        self._instances[current.provider_instance_id] = current
        return ReconcileResult(instance=current, changed=current.state != persisted.state)

    def connect_agent(self, instance: ProviderInstance) -> "DockerGuestAgent":
        docker_path = str(instance.opaque_state.get("docker_path") or self._require_docker_ready(frozenset({"sandbox.exec"})))
        name = str(instance.opaque_state.get("container_name") or instance.provider_instance_id)
        return DockerGuestAgent(
            docker_path=docker_path,
            container_name=name,
            runner=self._runner,
            output_bytes=_positive_int(instance.opaque_state.get("output_bytes")),
        )

    def _started(self, instance: ProviderInstance) -> ProviderInstance:
        started = ProviderInstance(
            provider_id=instance.provider_id,
            provider_instance_id=instance.provider_instance_id,
            sandbox_id=instance.sandbox_id,
            runtime_id=instance.runtime_id,
            state="ready",
            opaque_state=instance.opaque_state,
            generation=instance.generation + 1,
        )
        self._instances[started.provider_instance_id] = started
        return started

    def _inspect_state(self, docker_path: str, name: str) -> str | None:
        result = self._run([docker_path, "inspect", "--format", "{{.State.Status}}", name], timeout=10)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _require_docker_ready(self, required_capabilities: frozenset[str]) -> str:
        docker_path = self._docker_path()
        if docker_path is None:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                "Docker CLI was not found on PATH.",
                status_code=503,
            )
        status = self.doctor(RuntimeRequirements(provider_id=self.provider_id, required_capabilities=required_capabilities))
        if not status.ready:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                "Docker runtime is not ready.",
                status_code=503,
                details={
                    "missing_requirements": list(status.missing_requirements),
                    "diagnostics": [diagnostic.code for diagnostic in status.diagnostics],
                },
            )
        return docker_path

    def _docker_path(self) -> str | None:
        if self._configured_docker_path:
            return self._configured_docker_path
        return shutil.which("docker")

    def _run(self, command: Sequence[str], *, timeout: float | None = None, input_text: str | None = None) -> DockerCommandResult:
        try:
            return self._runner(tuple(command), input_text, timeout)
        except TimeoutError as exc:
            return DockerCommandResult(returncode=124, stderr=str(exc))
        except OSError as exc:
            return DockerCommandResult(returncode=127, stderr=str(exc))


class DockerGuestAgent:
    def __init__(
        self,
        *,
        docker_path: str,
        container_name: str,
        runner: DockerRunner,
        output_bytes: int | None,
    ) -> None:
        self._docker_path = docker_path
        self._container_name = container_name
        self._runner = runner
        self._output_bytes = output_bytes

    def exec(self, sandbox_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        request = GuestExecRequest.from_payload(payload)
        command = [self._docker_path, "exec"]
        if request.stdin is not None:
            command.append("--interactive")
        for key, value in sorted(request.env.items()):
            command.extend(["--env", f"{key}={value}"])
        command.extend(["--workdir", _container_cwd(request.cwd), self._container_name, *request.argv])
        try:
            result = self._runner(tuple(command), request.stdin, max(1, request.timeout_ms / 1000))
        except TimeoutError:
            return {
                "ok": False,
                "sandbox_id": sandbox_id,
                "code": "SANDBOX_EXEC_TIMEOUT",
                "error": "Sandbox exec timed out.",
                "status_code": 504,
                "client_request_id": request.client_request_id,
            }
        stdout, stdout_truncated = _bounded_output(result.stdout, self._output_bytes)
        stderr, stderr_truncated = _bounded_output(result.stderr, self._output_bytes)
        return {
            "ok": True,
            "sandbox_id": sandbox_id,
            "argv": list(request.argv),
            "cwd": request.cwd,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "client_request_id": request.client_request_id,
            "provider_runtime": "docker",
        }

    def capture_frame(self, sandbox_id: str, seat_id: str) -> dict[str, object]:
        return {
            "ok": False,
            "sandbox_id": sandbox_id,
            "seat_id": seat_id,
            "code": "SANDBOX_DESKTOP_NOT_AVAILABLE",
            "error": "Docker sandbox provider does not expose desktop capture.",
            "status_code": 501,
        }

    def desktop_input(
        self,
        sandbox_id: str,
        seat_id: str,
        payload: Mapping[str, object],
        *,
        actor: str = "human",
    ) -> dict[str, object]:
        del payload, actor
        return {
            "ok": False,
            "sandbox_id": sandbox_id,
            "seat_id": seat_id,
            "code": "SANDBOX_DESKTOP_NOT_AVAILABLE",
            "error": "Docker sandbox provider does not expose desktop input.",
            "status_code": 501,
        }


def _subprocess_runner(command: Sequence[str], input_text: str | None, timeout: float | None) -> DockerCommandResult:
    try:
        completed = subprocess.run(
            list(command),
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(str(exc)) from exc
    return DockerCommandResult(
        returncode=int(completed.returncode),
        stdout=str(completed.stdout or ""),
        stderr=str(completed.stderr or ""),
    )


def _docker_run_command(docker_path: str, name: str, opaque_state: Mapping[str, object]) -> list[str]:
    command = [
        docker_path,
        "run",
        "--detach",
        "--name",
        name,
        "--label",
        "rumi.managed_runtime=true",
        "--workdir",
        CONTAINER_WORKDIR,
        "--network",
        str(opaque_state.get("network_mode") or "none"),
    ]
    memory_mb = _positive_int(opaque_state.get("memory_mb"))
    if memory_mb:
        command.extend(["--memory", f"{memory_mb}m"])
    cpu_count = _positive_float(opaque_state.get("cpu_count"))
    if cpu_count:
        command.extend(["--cpus", str(cpu_count)])
    pids = _positive_int(opaque_state.get("pids"))
    if pids:
        command.extend(["--pids-limit", str(pids)])
    command.extend([str(opaque_state.get("image") or DEFAULT_DOCKER_IMAGE), "sleep", "infinity"])
    return command


def _image_for_spec(spec: SandboxCreateSpec) -> str:
    requested = str(spec.metadata.get("image") or "").strip()
    if spec.template.template_id == "coding.python" and (not requested or requested == DEFAULT_DOCKER_IMAGE):
        return CODING_PYTHON_IMAGE
    if spec.template.template_id == "coding.node" and (not requested or requested == DEFAULT_DOCKER_IMAGE):
        return CODING_NODE_IMAGE
    return requested or DEFAULT_DOCKER_IMAGE


def _docker_network_mode(spec: SandboxCreateSpec) -> str:
    if spec.template.network.mode in {"off", "deny", "none"}:
        return "none"
    if spec.template.network.approval_required:
        return "none"
    return "bridge"


def _container_name(sandbox_id: str) -> str:
    return f"rumi-sandbox-{sandbox_id}"


def _container_cwd(cwd: str) -> str:
    if cwd == ".":
        return CONTAINER_WORKDIR
    return (PurePosixPath(CONTAINER_WORKDIR) / cwd).as_posix()


def _docker_error(code: str, message: str, result: DockerCommandResult, *, status_code: int) -> SandboxContractError:
    return SandboxContractError(
        code,
        message,
        status_code=status_code,
        details={"exit_code": result.returncode, "stderr": result.stderr.strip()[:1000]},
    )


def _bounded_output(value: str, max_bytes: int | None) -> tuple[str, bool]:
    if not max_bytes or max_bytes <= 0:
        return value, False
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return value, False
    clipped = encoded[:max_bytes].decode("utf-8", errors="replace")
    return clipped, True


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _positive_float(value: object) -> float | None:
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
