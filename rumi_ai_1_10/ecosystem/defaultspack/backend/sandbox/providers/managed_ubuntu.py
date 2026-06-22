from __future__ import annotations

import base64
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable, Mapping, Sequence

from ..errors import RUNTIME_PROVIDER_UNAVAILABLE, SandboxContractError
from ..guest.protocol import DesktopInputRequest, GuestExecRequest
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
    model_to_dict,
)
from ..policy import validate_workspace_relative_path
from .base import ProgressSink


MANAGED_UBUNTU_CAPABILITIES = frozenset(
    {
        "sandbox.exec",
        "sandbox.files",
        "sandbox.overlay_workspace",
        "sandbox.port_forward",
        "sandbox.network_policy",
        "sandbox.resource_limits",
        "sandbox.desktop",
        "sandbox.desktop_input",
        "sandbox.snapshot",
    }
)
GUEST_WORKDIR = "/workspace"
GUEST_DEPS = ("Xvfb", "openbox", "xdotool", "import", "python3")
APT_PACKAGES = ("xvfb", "openbox", "xdotool", "imagemagick", "python3", "x11-utils", "ca-certificates")
DEFAULT_DISPLAY = ":98"
MAX_FILE_PATCH_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class GuestCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


CommandRunner = Callable[[Sequence[str], str | None, float | None], GuestCommandResult]


class ManagedUbuntuProvider:
    """Command-backed managed Ubuntu runtime used by Lima and WSL providers."""

    provider_id: str
    _host_platform: str
    _launcher_command: str

    def __init__(
        self,
        *,
        command_path: str | None = None,
        runner: CommandRunner | None = None,
        runtime_name: str = "rumi-managed-runtime",
    ) -> None:
        self._configured_command_path = command_path
        self._runner = runner or _subprocess_runner
        self._runtime_name = runtime_name
        self._instances: dict[str, ProviderInstance] = {}

    def doctor(self, request: RuntimeRequirements) -> RuntimeProviderStatus:
        host_platform = platform.system().lower() or "unknown"
        platform_ok = host_platform == self._host_platform
        command_path = self._command_path()
        diagnostics: list[Diagnostic] = []
        missing: list[str] = []
        version: str | None = None

        if not platform_ok:
            missing.append(f"platform:{self._host_platform}")
            diagnostics.append(
                Diagnostic(
                    code=f"{self.provider_id.upper()}_PLATFORM_UNAVAILABLE",
                    message=f"{self.provider_id} requires {self._host_platform}.",
                    severity="info",
                )
            )
        if command_path is None:
            missing.append(f"command:{self._launcher_command}")
            diagnostics.append(
                Diagnostic(
                    code=f"{self.provider_id.upper()}_COMMAND_MISSING",
                    message=f"{self._launcher_command} was not found on PATH.",
                    severity="warning",
                )
            )
        elif platform_ok:
            version_result = self._version(command_path)
            version = version_result.stdout.strip().splitlines()[0] if version_result.stdout.strip() else None

        guest_ready = False
        missing_deps: tuple[str, ...] = ()
        if platform_ok and command_path is not None:
            guest_ready = self._guest_exists(command_path)
            if not guest_ready:
                missing.append("managed_guest")
                diagnostics.append(
                    Diagnostic(
                        code=f"{self.provider_id.upper()}_GUEST_MISSING",
                        message="Managed Ubuntu guest is not created yet.",
                        severity="warning",
                    )
                )
            else:
                missing_deps = self._missing_guest_deps(command_path)
                if missing_deps:
                    missing.extend(f"guest_command:{name}" for name in missing_deps)
                    diagnostics.append(
                        Diagnostic(
                            code=f"{self.provider_id.upper()}_GUEST_DEPS_MISSING",
                            message="Managed Ubuntu guest is missing desktop helper packages.",
                            severity="warning",
                            details={"missing_commands": missing_deps},
                        )
                    )

        missing_capabilities = sorted(request.required_capabilities - MANAGED_UBUNTU_CAPABILITIES)
        missing.extend(missing_capabilities)
        ready = platform_ok and command_path is not None and guest_ready and not missing_deps and not missing_capabilities
        return RuntimeProviderStatus(
            provider_id=self.provider_id,
            platform=self._host_platform,
            available=platform_ok,
            installed=guest_ready and not missing_deps,
            ready=ready,
            version=version,
            capabilities=MANAGED_UBUNTU_CAPABILITIES if platform_ok else frozenset(),
            missing_requirements=tuple(missing),
            requires_user_action=not ready,
            user_action=None if ready else self._setup_message(),
            reboot_required=False,
            diagnostics=tuple(diagnostics),
        )

    def ensure(self, request: EnsureRuntimeRequest, progress: ProgressSink) -> OperationResult:
        command_path = self._command_path()
        if command_path is None or platform.system().lower() != self._host_platform:
            status = self.doctor(request.requirements)
            return OperationResult(
                ok=False,
                provider_id=self.provider_id,
                operation_id=f"{self.provider_id}-ensure",
                status="failed",
                diagnostics=status.diagnostics,
                requires_user_action=True,
                user_action=status.user_action,
                reboot_required=status.reboot_required,
            )

        try:
            progress.emit(ProgressEvent(operation_id=f"{self.provider_id}-ensure", stage="guest", message="Creating or starting managed Ubuntu guest", percent=15))
            self._ensure_guest(command_path)
            progress.emit(ProgressEvent(operation_id=f"{self.provider_id}-ensure", stage="packages", message="Installing managed runtime guest packages", percent=55))
            self._install_guest_packages(command_path)
            status = self.doctor(request.requirements)
        except SandboxContractError as exc:
            return OperationResult(
                ok=False,
                provider_id=self.provider_id,
                operation_id=f"{self.provider_id}-ensure",
                status="failed",
                diagnostics=(Diagnostic(code=exc.code, message=exc.message, severity="error", details=exc.details),),
                requires_user_action=True,
                user_action=exc.message,
            )

        if status.ready:
            progress.emit(ProgressEvent(operation_id=f"{self.provider_id}-ensure", stage="ready", message="Managed Ubuntu runtime is ready", percent=100))
            return OperationResult(ok=True, provider_id=self.provider_id, operation_id=f"{self.provider_id}-ensure", status="completed")
        return OperationResult(
            ok=False,
            provider_id=self.provider_id,
            operation_id=f"{self.provider_id}-ensure",
            status="failed",
            diagnostics=status.diagnostics,
            requires_user_action=True,
            user_action=status.user_action,
        )

    def update(self, request: UpdateRuntimeRequest, progress: ProgressSink) -> OperationResult:
        del request
        command_path = self._require_command()
        progress.emit(ProgressEvent(operation_id=f"{self.provider_id}-update", stage="packages", message="Updating managed Ubuntu guest packages", percent=50))
        self._install_guest_packages(command_path, update=True)
        progress.emit(ProgressEvent(operation_id=f"{self.provider_id}-update", stage="ready", message="Managed Ubuntu runtime packages are current", percent=100))
        return OperationResult(ok=True, provider_id=self.provider_id, operation_id=f"{self.provider_id}-update", status="completed")

    def uninstall(self, request: UninstallRuntimeRequest, progress: ProgressSink) -> OperationResult:
        command_path = self._require_command()
        for instance in list(self._instances.values()):
            self.destroy(instance)
        self._stop_guest(command_path)
        if request.remove_state:
            self._delete_guest(command_path)
        progress.emit(ProgressEvent(operation_id=f"{self.provider_id}-uninstall", stage="stopped", message="Stopped managed Ubuntu runtime", percent=100))
        return OperationResult(ok=True, provider_id=self.provider_id, operation_id=f"{self.provider_id}-uninstall", status="completed")

    def create(self, spec: SandboxCreateSpec) -> ProviderInstance:
        command_path = self._require_ready(spec.template.provider_requirements)
        sandbox_id = str(uuid.uuid4())
        desktop = spec.template.desktop
        width = int(desktop.width if desktop else 1440)
        height = int(desktop.height if desktop else 900)
        opaque = {
            "command_path": command_path,
            "runtime_name": self._runtime_name,
            "template_id": spec.template.template_id,
            "width": width,
            "height": height,
            "desktop_enabled": desktop is not None and desktop.enabled,
            "display": DEFAULT_DISPLAY,
            "workspace_binding": model_to_dict(spec.workspace_binding),
            "network_policy": model_to_dict(spec.template.network),
            "resource_limits": model_to_dict(spec.template.resources),
            "desktop_provisioning": spec.metadata.get("desktop_provisioning") or {},
            "desktop_rules": spec.metadata.get("desktop_rules") or {},
            "assigned_agent_id": spec.metadata.get("assigned_agent_id"),
            "startup": spec.metadata.get("startup") or {},
        }
        instance = ProviderInstance(
            provider_id=self.provider_id,
            provider_instance_id=f"{self.provider_id}-{sandbox_id}",
            sandbox_id=sandbox_id,
            runtime_id=self._runtime_name,
            state="stopped",
            opaque_state=opaque,
        )
        self._instances[instance.provider_instance_id] = instance
        return instance

    def start(self, instance: ProviderInstance) -> ProviderInstance:
        command_path = str(instance.opaque_state.get("command_path") or self._require_ready(MANAGED_UBUNTU_CAPABILITIES))
        if instance.opaque_state.get("desktop_enabled") is True:
            self._guest_shell(
                command_path,
                _desktop_start_script(
                    instance.provider_instance_id,
                    _positive_int(instance.opaque_state.get("width"), 1440),
                    _positive_int(instance.opaque_state.get("height"), 900),
                    str(instance.opaque_state.get("display") or DEFAULT_DISPLAY),
                ),
                timeout=30,
            )
        else:
            self._guest_shell(command_path, "mkdir -p /workspace", timeout=15)
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

    def stop(self, instance: ProviderInstance, *, force: bool = False) -> None:
        del force
        command_path = str(instance.opaque_state.get("command_path") or self._command_path() or self._launcher_command)
        self._guest_shell(command_path, _desktop_stop_script(instance.provider_instance_id), timeout=15, check=False)
        stopped = ProviderInstance(
            provider_id=instance.provider_id,
            provider_instance_id=instance.provider_instance_id,
            sandbox_id=instance.sandbox_id,
            runtime_id=instance.runtime_id,
            state="stopped",
            opaque_state=instance.opaque_state,
            generation=instance.generation + 1,
        )
        self._instances[stopped.provider_instance_id] = stopped

    def destroy(self, instance: ProviderInstance) -> None:
        self.stop(instance, force=True)
        self._instances.pop(instance.provider_instance_id, None)

    def reconcile(self, persisted: ProviderInstance) -> ReconcileResult:
        command_path = str(persisted.opaque_state.get("command_path") or self._command_path() or self._launcher_command)
        running = self._desktop_running(command_path, persisted.provider_instance_id)
        state = "ready" if running else "stopped"
        current = ProviderInstance(
            provider_id=persisted.provider_id,
            provider_instance_id=persisted.provider_instance_id,
            sandbox_id=persisted.sandbox_id,
            runtime_id=persisted.runtime_id,
            state=state,
            opaque_state=persisted.opaque_state,
            generation=persisted.generation,
        )
        self._instances[current.provider_instance_id] = current
        return ReconcileResult(instance=current, changed=current.state != persisted.state)

    def connect_agent(self, instance: ProviderInstance) -> "ManagedUbuntuGuestAgent":
        command_path = str(instance.opaque_state.get("command_path") or self._require_ready(MANAGED_UBUNTU_CAPABILITIES))
        resources = instance.opaque_state.get("resource_limits") if isinstance(instance.opaque_state.get("resource_limits"), Mapping) else {}
        return ManagedUbuntuGuestAgent(
            provider_id=self.provider_id,
            command_path=command_path,
            command_prefix=self._guest_prefix(command_path),
            runner=self._runner,
            display=str(instance.opaque_state.get("display") or DEFAULT_DISPLAY),
            width=_positive_int(instance.opaque_state.get("width"), 1440),
            height=_positive_int(instance.opaque_state.get("height"), 900),
            output_bytes=_optional_positive_int(resources.get("output_bytes")),
            timeout_ms=_optional_positive_int(resources.get("timeout_ms")),
        )

    def _command_path(self) -> str | None:
        if self._configured_command_path:
            return self._configured_command_path
        return shutil.which(self._launcher_command)

    def _require_command(self) -> str:
        command_path = self._command_path()
        if command_path is None:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                f"{self._launcher_command} was not found on PATH.",
                status_code=503,
            )
        return command_path

    def _require_ready(self, required_capabilities: frozenset[str]) -> str:
        command_path = self._require_command()
        status = self.doctor(RuntimeRequirements(provider_id=self.provider_id, required_capabilities=required_capabilities))
        if not status.ready:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                f"Managed runtime provider is not ready: {self.provider_id}",
                status_code=503,
                details={"missing_requirements": list(status.missing_requirements)},
            )
        return command_path

    def _version(self, command_path: str) -> GuestCommandResult:
        return self._run(self._version_command(command_path), timeout=5)

    def _run(self, command: Sequence[str], input_text: str | None = None, timeout: float | None = None) -> GuestCommandResult:
        try:
            return self._runner(tuple(command), input_text, timeout)
        except TimeoutError as exc:
            return GuestCommandResult(returncode=124, stderr=str(exc))
        except OSError as exc:
            return GuestCommandResult(returncode=127, stderr=str(exc))

    def _guest_command(
        self,
        command_path: str,
        argv: Sequence[str],
        *,
        input_text: str | None = None,
        timeout: float | None = None,
        check: bool = True,
    ) -> GuestCommandResult:
        result = self._run((*self._guest_prefix(command_path), *argv), input_text=input_text, timeout=timeout)
        if check and result.returncode != 0:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                "Managed Ubuntu guest command failed.",
                status_code=503,
                details={"stderr": result.stderr.strip()[:1000], "argv": list(argv[:4])},
            )
        return result

    def _guest_shell(self, command_path: str, script: str, *, timeout: float | None = None, check: bool = True) -> GuestCommandResult:
        return self._guest_command(command_path, ("bash", "-lc", script), timeout=timeout, check=check)

    def _missing_guest_deps(self, command_path: str) -> tuple[str, ...]:
        script = "\n".join(f"command -v {name} >/dev/null 2>&1 || echo {name}" for name in GUEST_DEPS)
        result = self._guest_shell(command_path, script, timeout=10, check=False)
        if result.returncode != 0:
            return GUEST_DEPS
        return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())

    def _install_guest_packages(self, command_path: str, *, update: bool = False) -> None:
        packages = " ".join(APT_PACKAGES)
        script = (
            "set -e\n"
            "export DEBIAN_FRONTEND=noninteractive\n"
            "sudo apt-get update\n"
            f"sudo apt-get install -y {packages}\n"
        )
        if update:
            script += f"sudo apt-get install --only-upgrade -y {packages} || true\n"
        self._guest_shell(command_path, script, timeout=600)

    def _desktop_running(self, command_path: str, provider_instance_id: str) -> bool:
        result = self._guest_shell(command_path, _desktop_running_script(provider_instance_id), timeout=10, check=False)
        return result.returncode == 0

    def _setup_message(self) -> str:
        return "Open the managed runtime setup flow to create and provision the Ubuntu guest."

    def _guest_exists(self, command_path: str) -> bool:
        raise NotImplementedError

    def _ensure_guest(self, command_path: str) -> None:
        raise NotImplementedError

    def _stop_guest(self, command_path: str) -> None:
        raise NotImplementedError

    def _delete_guest(self, command_path: str) -> None:
        raise NotImplementedError

    def _guest_prefix(self, command_path: str) -> tuple[str, ...]:
        raise NotImplementedError

    def _version_command(self, command_path: str) -> tuple[str, ...]:
        raise NotImplementedError


class MacLimaProvider(ManagedUbuntuProvider):
    provider_id = "mac_lima"
    _host_platform = "darwin"
    _launcher_command = "limactl"

    def _guest_exists(self, command_path: str) -> bool:
        result = self._run((command_path, "list", "--format", "{{.Name}}"), timeout=10)
        return result.returncode == 0 and self._runtime_name in {line.strip() for line in result.stdout.splitlines()}

    def _ensure_guest(self, command_path: str) -> None:
        if self._guest_exists(command_path):
            self._run((command_path, "start", self._runtime_name), timeout=120)
            return
        config_path = _write_lima_config()
        try:
            result = self._run((command_path, "start", "--name", self._runtime_name, config_path), timeout=900)
        finally:
            _unlink(config_path)
        if result.returncode != 0:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                "Lima managed Ubuntu guest could not be created.",
                status_code=503,
                details={"stderr": result.stderr.strip()[:1000]},
            )

    def _stop_guest(self, command_path: str) -> None:
        self._run((command_path, "stop", "--force", self._runtime_name), timeout=60)

    def _delete_guest(self, command_path: str) -> None:
        self._run((command_path, "delete", "--force", self._runtime_name), timeout=120)

    def _guest_prefix(self, command_path: str) -> tuple[str, ...]:
        return (command_path, "shell", self._runtime_name, "--")

    def _version_command(self, command_path: str) -> tuple[str, ...]:
        return (command_path, "--version")


class WindowsWslProvider(ManagedUbuntuProvider):
    provider_id = "windows_wsl"
    _host_platform = "windows"
    _launcher_command = "wsl.exe"

    def __init__(
        self,
        *,
        command_path: str | None = None,
        runner: CommandRunner | None = None,
        runtime_name: str = "Ubuntu",
    ) -> None:
        super().__init__(command_path=command_path, runner=runner, runtime_name=runtime_name)

    def _guest_exists(self, command_path: str) -> bool:
        result = self._run((command_path, "-l", "-q"), timeout=10)
        return result.returncode == 0 and self._runtime_name.casefold() in {line.strip().casefold() for line in result.stdout.splitlines()}

    def _ensure_guest(self, command_path: str) -> None:
        if self._guest_exists(command_path):
            return
        result = self._run((command_path, "--install", "-d", self._runtime_name), timeout=900)
        if result.returncode != 0:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                "WSL Ubuntu distribution could not be installed.",
                status_code=503,
                details={"stderr": result.stderr.strip()[:1000]},
            )

    def _stop_guest(self, command_path: str) -> None:
        self._run((command_path, "--terminate", self._runtime_name), timeout=60)

    def _delete_guest(self, command_path: str) -> None:
        self._run((command_path, "--unregister", self._runtime_name), timeout=120)

    def _guest_prefix(self, command_path: str) -> tuple[str, ...]:
        return (command_path, "-d", self._runtime_name, "--")

    def _version_command(self, command_path: str) -> tuple[str, ...]:
        return (command_path, "--version")


class ManagedUbuntuGuestAgent:
    def __init__(
        self,
        *,
        provider_id: str,
        command_path: str,
        command_prefix: Sequence[str],
        runner: CommandRunner,
        display: str,
        width: int,
        height: int,
        output_bytes: int | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._command_path = command_path
        self._command_prefix = tuple(command_prefix)
        self._runner = runner
        self._display = display
        self._width = width
        self._height = height
        self._output_bytes = output_bytes
        self._timeout_ms = timeout_ms

    def exec(self, sandbox_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        request = GuestExecRequest.from_payload(payload)
        timeout_ms = min(request.timeout_ms, self._timeout_ms) if self._timeout_ms else request.timeout_ms
        result = self._run(_exec_argv(request.cwd, request.argv), input_text=request.stdin, timeout=max(1, timeout_ms / 1000))
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
            "provider_runtime": self._provider_id,
        }

    def apply_file_patch(self, sandbox_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        operations = _file_patch_operations(payload)
        applied: list[dict[str, object]] = []
        for operation in operations:
            path = str(operation["path"])
            content = operation["content"]
            parent = _container_parent(path)
            if parent:
                mkdir = self._run(("mkdir", "-p", parent), timeout=30)
                if mkdir.returncode != 0:
                    return _guest_error(sandbox_id, "SANDBOX_FILES_FAILED", "Sandbox file patch could not create parent directory.", mkdir)
            encoded = base64.b64encode(content).decode("ascii")
            script = (
                "import base64, pathlib, sys\n"
                "path = pathlib.Path(sys.argv[1])\n"
                "path.write_bytes(base64.b64decode(sys.stdin.read().encode('ascii')))\n"
            )
            write = self._run(("python3", "-c", script, _container_path(path)), input_text=encoded, timeout=60)
            if write.returncode != 0:
                return _guest_error(sandbox_id, "SANDBOX_FILES_FAILED", "Sandbox file patch could not write content.", write)
            applied.append({"path": path, "bytes": len(content)})
        return {
            "ok": True,
            "sandbox_id": sandbox_id,
            "applied": applied,
            "files_written": len(applied),
            "provider_runtime": self._provider_id,
        }

    def expose_port(self, sandbox_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        port = _port_number(payload.get("port"))
        protocol = str(payload.get("protocol") or "http").strip().lower()
        if protocol not in {"http", "https", "tcp"}:
            raise SandboxContractError("INVALID_SANDBOX_PORT", "Sandbox port protocol must be http, https, or tcp.", status_code=400)
        scheme = "http" if protocol == "tcp" else protocol
        url = f"{scheme}://127.0.0.1:{port}"
        return {
            "ok": True,
            "sandbox_id": sandbox_id,
            "port": port,
            "protocol": protocol,
            "url": url,
            "target_url": url,
            "host_reachable": True,
            "provider_runtime": self._provider_id,
        }

    def capture_frame(self, sandbox_id: str, seat_id: str) -> dict[str, object]:
        result = self._run(("env", f"DISPLAY={self._display}", "bash", "-lc", "import -window root png:- | base64 -w0"), timeout=30)
        if result.returncode != 0:
            return _guest_error(sandbox_id, "SANDBOX_SCREENSHOT_FAILED", "Desktop frame capture failed.", result)
        try:
            data = base64.b64decode(result.stdout.strip(), validate=True)
        except Exception as exc:
            raise SandboxContractError("SANDBOX_SCREENSHOT_FAILED", "Desktop frame capture returned invalid image data.", status_code=502) from exc
        return {
            "ok": True,
            "sandbox_id": sandbox_id,
            "seat_id": seat_id,
            "content_type": "image/png",
            "data": data,
            "width": self._width,
            "height": self._height,
            "source": self._provider_id,
        }

    def desktop_input(
        self,
        sandbox_id: str,
        seat_id: str,
        payload: Mapping[str, object],
        *,
        actor: str = "human",
    ) -> dict[str, object]:
        request = DesktopInputRequest.from_payload(payload, width=self._width, height=self._height, require_lease=False)
        result = self._dispatch_input(request)
        return {
            "ok": result.returncode == 0,
            "sandbox_id": sandbox_id,
            "seat_id": seat_id,
            "action": request.action,
            "actor": actor,
            "error": result.stderr or None,
            "provider_runtime": self._provider_id,
        }

    def _dispatch_input(self, request: DesktopInputRequest) -> GuestCommandResult:
        prefix = ("env", f"DISPLAY={self._display}", "xdotool")
        if request.action == "move":
            return self._run((*prefix, "mousemove", str(int(request.x)), str(int(request.y))), timeout=10)
        if request.action == "click":
            return self._run((*prefix, "mousemove", str(int(request.x)), str(int(request.y)), "click", _button(request.button)), timeout=10)
        if request.action == "double_click":
            return self._run((*prefix, "mousemove", str(int(request.x)), str(int(request.y)), "click", "--repeat", "2", _button(request.button)), timeout=10)
        if request.action == "drag":
            return self._run((*prefix, "mousemove", str(int(request.x)), str(int(request.y)), "mousedown", _button(request.button), "mousemove", str(int(request.to_x)), str(int(request.to_y)), "mouseup", _button(request.button)), timeout=15)
        if request.action == "scroll":
            clicks = max(1, abs(int(request.delta_y or request.delta_x or 1)))
            button = "5" if int(request.delta_y or 0) >= 0 else "4"
            return self._run((*prefix, "mousemove", str(int(request.x or 0)), str(int(request.y or 0)), "click", "--repeat", str(clicks), button), timeout=10)
        if request.action == "type_text":
            return self._run((*prefix, "type", "--", str(request.text or "")), timeout=30)
        if request.action == "key":
            return self._run((*prefix, "key", str(request.key or "")), timeout=10)
        return GuestCommandResult(returncode=1, stderr="Unsupported desktop input action.")

    def _run(self, argv: Sequence[str], input_text: str | None = None, timeout: float | None = None) -> GuestCommandResult:
        try:
            return self._runner((*self._command_prefix, *argv), input_text, timeout)
        except TimeoutError as exc:
            return GuestCommandResult(returncode=124, stderr=str(exc))
        except OSError as exc:
            return GuestCommandResult(returncode=127, stderr=str(exc))


def _subprocess_runner(command: Sequence[str], input_text: str | None, timeout: float | None) -> GuestCommandResult:
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
    return GuestCommandResult(
        returncode=int(completed.returncode),
        stdout=str(completed.stdout or ""),
        stderr=str(completed.stderr or ""),
    )


def _write_lima_config() -> str:
    content = """images:
- location: https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
  arch: x86_64
- location: https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-arm64.img
  arch: aarch64
mounts: []
networks: []
provision:
- mode: system
  script: |
    #!/bin/sh
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y xvfb openbox xdotool imagemagick python3 x11-utils ca-certificates
"""
    handle = tempfile.NamedTemporaryFile(prefix="rumi-lima-", suffix=".yaml", delete=False)
    try:
        handle.write(content.encode("utf-8"))
        return handle.name
    finally:
        handle.close()


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _desktop_start_script(provider_instance_id: str, width: int, height: int, display: str) -> str:
    runtime_dir = _runtime_dir(provider_instance_id)
    return (
        "set -e\n"
        "mkdir -p /workspace " + runtime_dir + "\n"
        f"DISPLAY_ID={display!r}\n"
        f"if [ ! -f {runtime_dir}/xvfb.pid ] || ! kill -0 $(cat {runtime_dir}/xvfb.pid) >/dev/null 2>&1; then\n"
        f"  Xvfb {display} -screen 0 {width}x{height}x24 -nolisten tcp >{runtime_dir}/xvfb.log 2>&1 & echo $! > {runtime_dir}/xvfb.pid\n"
        "  sleep 0.5\n"
        "fi\n"
        f"if [ ! -f {runtime_dir}/openbox.pid ] || ! kill -0 $(cat {runtime_dir}/openbox.pid) >/dev/null 2>&1; then\n"
        f"  DISPLAY={display} openbox >{runtime_dir}/openbox.log 2>&1 & echo $! > {runtime_dir}/openbox.pid\n"
        "fi\n"
    )


def _desktop_stop_script(provider_instance_id: str) -> str:
    runtime_dir = _runtime_dir(provider_instance_id)
    return (
        "set +e\n"
        f"for pidfile in {runtime_dir}/openbox.pid {runtime_dir}/xvfb.pid; do\n"
        "  if [ -f \"$pidfile\" ]; then kill $(cat \"$pidfile\") >/dev/null 2>&1 || true; rm -f \"$pidfile\"; fi\n"
        "done\n"
    )


def _desktop_running_script(provider_instance_id: str) -> str:
    runtime_dir = _runtime_dir(provider_instance_id)
    return f"test -f {runtime_dir}/xvfb.pid && kill -0 $(cat {runtime_dir}/xvfb.pid)"


def _runtime_dir(provider_instance_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in provider_instance_id)
    return f"/tmp/rumi-managed-runtime/{safe}"


def _exec_argv(cwd: str, argv: Sequence[str]) -> tuple[str, ...]:
    if cwd == ".":
        return tuple(argv)
    return ("bash", "-lc", 'cd "$1" && shift && exec "$@"', "rumi-cd", _container_path(cwd), *argv)


def _container_path(path: str) -> str:
    return (PurePosixPath(GUEST_WORKDIR) / path).as_posix()


def _container_parent(path: str) -> str | None:
    parent = PurePosixPath(_container_path(path)).parent
    return None if parent.as_posix() == GUEST_WORKDIR else parent.as_posix()


def _file_patch_operations(payload: Mapping[str, object]) -> list[dict[str, object]]:
    raw_items = payload.get("files")
    if raw_items is None:
        raw_items = payload.get("patch")
    if raw_items is None:
        raw_items = [payload]
    if not isinstance(raw_items, list) or not raw_items:
        raise SandboxContractError("INVALID_SANDBOX_FILE_PATCH", "Sandbox file patch requires at least one file operation.", status_code=400)

    operations: list[dict[str, object]] = []
    total_bytes = 0
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            raise SandboxContractError("INVALID_SANDBOX_FILE_PATCH", "Sandbox file patch operations must be objects.", status_code=400)
        path = validate_workspace_relative_path(raw.get("path"), field="path")
        op = str(raw.get("op") or raw.get("operation") or "write").strip().lower()
        if op not in {"write", "replace", "create", "upsert"}:
            raise SandboxContractError("INVALID_SANDBOX_FILE_PATCH", "Sandbox file patch only supports write-style operations.", status_code=400)
        content = _patch_content(raw)
        total_bytes += len(content)
        if total_bytes > MAX_FILE_PATCH_BYTES:
            raise SandboxContractError("SANDBOX_FILE_PATCH_TOO_LARGE", "Sandbox file patch payload is too large.", status_code=413)
        operations.append({"path": path, "content": content})
    return operations


def _patch_content(raw: Mapping[str, object]) -> bytes:
    if "content_base64" in raw:
        value = raw.get("content_base64")
        if not isinstance(value, str):
            raise SandboxContractError("INVALID_SANDBOX_FILE_PATCH", "content_base64 must be a string.", status_code=400)
        try:
            return base64.b64decode(value, validate=True)
        except Exception as exc:
            raise SandboxContractError("INVALID_SANDBOX_FILE_PATCH", "content_base64 is invalid.", status_code=400) from exc
    value = raw.get("content")
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise SandboxContractError("INVALID_SANDBOX_FILE_PATCH", "Sandbox file patch requires content or content_base64.", status_code=400)


def _port_number(value: object) -> int:
    if isinstance(value, bool):
        raise SandboxContractError("INVALID_SANDBOX_PORT", "Sandbox port must be an integer.", status_code=400)
    try:
        port = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise SandboxContractError("INVALID_SANDBOX_PORT", "Sandbox port must be an integer.", status_code=400) from exc
    if port < 1 or port > 65535:
        raise SandboxContractError("INVALID_SANDBOX_PORT", "Sandbox port must be between 1 and 65535.", status_code=400)
    return port


def _positive_int(value: object, fallback: int) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _optional_positive_int(value: object) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _bounded_output(value: str, max_bytes: int | None) -> tuple[str, bool]:
    if not max_bytes or max_bytes <= 0:
        return value, False
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return value, False
    return encoded[:max_bytes].decode("utf-8", errors="replace"), True


def _button(value: object) -> str:
    return {"left": "1", "middle": "2", "right": "3"}.get(str(value or "left").lower(), "1")


def _guest_error(sandbox_id: str, code: str, message: str, result: GuestCommandResult) -> dict[str, object]:
    return {
        "ok": False,
        "sandbox_id": sandbox_id,
        "code": code,
        "error": message,
        "status_code": 502,
        "details": {"stderr": result.stderr.strip()[:1000]},
    }
