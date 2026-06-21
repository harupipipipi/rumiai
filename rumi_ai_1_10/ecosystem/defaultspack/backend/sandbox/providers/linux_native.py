from __future__ import annotations

import base64
from pathlib import Path
import sys
import uuid
from typing import Any, Mapping

from ..errors import INVALID_EXEC_REQUEST, RUNTIME_PROVIDER_UNAVAILABLE, SandboxContractError
from ..guest.protocol import DesktopInputRequest
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


DESKTOP_CAPABILITIES = frozenset({"sandbox.desktop", "sandbox.desktop_input", "sandbox.snapshot"})


class LinuxNativeProvider:
    """Provider for a Rumi-owned Linux Xvfb/Openbox desktop seat.

    This provider deliberately does not advertise sandbox.exec/files until a
    real Linux isolation layer is wired. The desktop path runs only the owned
    X11 helper and never falls back to arbitrary host command execution.
    """

    provider_id = "linux_native"

    def __init__(self, *, session_factory: Any | None = None) -> None:
        self._session_factory = session_factory
        self._instances: dict[str, ProviderInstance] = {}
        self._sessions: dict[str, Any] = {}

    def doctor(self, request: RuntimeRequirements) -> RuntimeProviderStatus:
        available = sys.platform.startswith("linux")
        capabilities = DESKTOP_CAPABILITIES if available else frozenset()
        missing: list[str] = []
        diagnostics: list[Diagnostic] = []
        installed = False

        if not available:
            missing.append("linux_platform")
            diagnostics.append(
                Diagnostic(
                    code="LINUX_NATIVE_PLATFORM_UNAVAILABLE",
                    message="Linux native desktops require a Linux host or guest runtime.",
                    severity="warning",
                )
            )
        else:
            session = self._new_session()
            missing_commands = list(session.missing_commands())
            installed = not missing_commands
            if missing_commands:
                missing.extend(f"command:{name}" for name in missing_commands)
                diagnostics.append(
                    Diagnostic(
                        code="LINUX_NATIVE_COMMANDS_MISSING",
                        message="Linux native desktop helper commands are not available in the runtime.",
                        severity="warning",
                        details={"missing_commands": missing_commands},
                    )
                )

        missing_capabilities = sorted(request.required_capabilities - capabilities)
        missing.extend(missing_capabilities)
        ready = available and installed and not missing_capabilities
        return RuntimeProviderStatus(
            provider_id=self.provider_id,
            platform="linux",
            available=available,
            installed=installed,
            ready=ready,
            version=None,
            capabilities=capabilities,
            missing_requirements=tuple(missing),
            requires_user_action=bool(missing),
            user_action=None if ready else "Open the managed runtime setup flow to install the Linux desktop helper.",
            reboot_required=False,
            diagnostics=tuple(diagnostics),
        )

    def ensure(self, request: EnsureRuntimeRequest, progress: ProgressSink) -> OperationResult:
        progress.emit(ProgressEvent(operation_id="linux-native-ensure", stage="doctor", message="Checking Linux native desktop runtime"))
        status = self.doctor(request.requirements)
        if status.ready:
            progress.emit(ProgressEvent(operation_id="linux-native-ensure", stage="ready", message="Linux native desktop runtime is ready", percent=100))
            return OperationResult(ok=True, provider_id=self.provider_id, operation_id="linux-native-ensure", status="completed")
        return OperationResult(
            ok=False,
            provider_id=self.provider_id,
            operation_id="linux-native-ensure",
            status="failed",
            diagnostics=status.diagnostics,
            requires_user_action=status.requires_user_action,
            user_action=status.user_action,
            reboot_required=status.reboot_required,
        )

    def update(self, request: UpdateRuntimeRequest, progress: ProgressSink) -> OperationResult:
        del request
        progress.emit(ProgressEvent(operation_id="linux-native-update", stage="not_ready", message="Linux native desktop runtime has no bundled updater yet", percent=0))
        return OperationResult(
            ok=False,
            provider_id=self.provider_id,
            operation_id="linux-native-update",
            status="failed",
            requires_user_action=True,
            user_action="Linux native runtime update is not implemented in this build.",
        )

    def uninstall(self, request: UninstallRuntimeRequest, progress: ProgressSink) -> OperationResult:
        del request
        for instance in list(self._instances.values()):
            self.destroy(instance)
        progress.emit(ProgressEvent(operation_id="linux-native-uninstall", stage="stopped", message="Stopped Linux native desktop sessions", percent=100))
        return OperationResult(ok=True, provider_id=self.provider_id, operation_id="linux-native-uninstall", status="completed")

    def create(self, spec: SandboxCreateSpec) -> ProviderInstance:
        if spec.template.desktop is None or not spec.template.desktop.enabled:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                "Linux native provider only supports desktop templates in this build.",
                status_code=503,
            )
        sandbox_id = str(uuid.uuid4())
        session = self._new_session(width=spec.template.desktop.width, height=spec.template.desktop.height)
        instance = ProviderInstance(
            provider_id=self.provider_id,
            provider_instance_id=f"linux-native-{sandbox_id}",
            sandbox_id=sandbox_id,
            runtime_id="linux-native-x11",
            state="stopped",
            opaque_state={
                "template_id": spec.template.template_id,
                "width": spec.template.desktop.width,
                "height": spec.template.desktop.height,
            },
        )
        self._instances[instance.provider_instance_id] = instance
        self._sessions[instance.provider_instance_id] = session
        return instance

    def start(self, instance: ProviderInstance) -> ProviderInstance:
        session = self._require_session(instance)
        status = session.start()
        if not status.get("running"):
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                str(status.get("reason") or "Linux native desktop session did not start."),
                status_code=503,
                details={"status": status},
            )
        started = ProviderInstance(
            provider_id=instance.provider_id,
            provider_instance_id=instance.provider_instance_id,
            sandbox_id=instance.sandbox_id,
            runtime_id=instance.runtime_id,
            state="ready",
            opaque_state={**dict(instance.opaque_state), "display": session.display},
            generation=instance.generation + 1,
        )
        self._instances[started.provider_instance_id] = started
        return started

    def stop(self, instance: ProviderInstance, *, force: bool = False) -> None:
        del force
        session = self._sessions.get(instance.provider_instance_id)
        if session is not None:
            session.stop()
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
        session = self._sessions.pop(instance.provider_instance_id, None)
        if session is not None:
            session.stop()
        self._instances.pop(instance.provider_instance_id, None)

    def reconcile(self, persisted: ProviderInstance) -> ReconcileResult:
        current = self._instances.get(persisted.provider_instance_id)
        if current is None:
            current = ProviderInstance(
                provider_id=persisted.provider_id,
                provider_instance_id=persisted.provider_instance_id,
                sandbox_id=persisted.sandbox_id,
                runtime_id=persisted.runtime_id,
                state="stopped",
                opaque_state=persisted.opaque_state,
                generation=persisted.generation,
            )
        return ReconcileResult(instance=current, changed=current != persisted)

    def connect_agent(self, instance: ProviderInstance) -> "LinuxNativeGuestAgent":
        return LinuxNativeGuestAgent(self._require_session(instance))

    def _require_session(self, instance: ProviderInstance) -> Any:
        session = self._sessions.get(instance.provider_instance_id)
        if session is None:
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                "Linux native desktop session is not available in this process.",
                status_code=503,
            )
        return session

    def _new_session(self, *, width: int | None = None, height: int | None = None) -> Any:
        if self._session_factory is not None:
            return self._session_factory(width=width, height=height)
        from ecosystem.rumi_default_tools_pack.domain.computer.linux.x11_virtual import (
            X11VirtualSession,
            X11VirtualSessionConfig,
        )

        config = X11VirtualSessionConfig(width=width or 1440, height=height or 900)
        return X11VirtualSession(config)


class LinuxNativeGuestAgent:
    def __init__(self, session: Any) -> None:
        self._session = session

    def exec(self, sandbox_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        del sandbox_id, payload
        raise SandboxContractError(
            INVALID_EXEC_REQUEST,
            "Linux native desktop provider does not expose sandbox exec in this build.",
            status_code=501,
        )

    def capture_frame(self, sandbox_id: str, seat_id: str) -> dict[str, object]:
        screenshot = self._session.screenshot()
        screenshot_path = str(screenshot.get("path") or "")
        data_url = str(screenshot.get("data_url") or "")
        response: dict[str, object] | None = None
        try:
            if not data_url.startswith("data:image/png;base64,"):
                return {
                    "ok": False,
                    "sandbox_id": sandbox_id,
                    "seat_id": seat_id,
                    "error": str(screenshot.get("reason") or screenshot.get("error") or "Desktop frame capture failed."),
                }
            data = base64.b64decode(data_url.split(",", 1)[1])
            response = {
                "ok": True,
                "sandbox_id": sandbox_id,
                "seat_id": seat_id,
                "content_type": "image/png",
                "data": data,
                "width": int(getattr(self._session.config, "width", 0) or 0),
                "height": int(getattr(self._session.config, "height", 0) or 0),
                "source": "linux_native_x11",
                "metadata": {
                    "display": getattr(self._session, "display", None),
                    "path": screenshot_path or None,
                    "path_deleted": False,
                },
            }
            return response
        finally:
            path_deleted = _unlink_capture_file(screenshot_path)
            metadata = response.get("metadata") if response is not None else None
            if isinstance(metadata, dict):
                metadata["path_deleted"] = path_deleted

    def desktop_input(
        self,
        sandbox_id: str,
        seat_id: str,
        payload: Mapping[str, object],
        *,
        actor: str = "human",
    ) -> dict[str, object]:
        del actor
        request = DesktopInputRequest.from_payload(
            payload,
            width=int(getattr(self._session.config, "width", 0) or 0),
            height=int(getattr(self._session.config, "height", 0) or 0),
            require_lease=False,
        )
        result = self._dispatch_input(request)
        return {
            "ok": bool(result.get("executed")),
            "sandbox_id": sandbox_id,
            "seat_id": seat_id,
            "action": request.action,
            "error": result.get("reason") or result.get("error") or result.get("stderr"),
        }

    def _dispatch_input(self, request: DesktopInputRequest) -> dict[str, Any]:
        if request.action == "move":
            return self._session.move(int(request.x), int(request.y))
        if request.action == "click":
            return self._session.click(int(request.x), int(request.y), button=str(request.button or "left"))
        if request.action == "double_click":
            return self._session.double_click(int(request.x), int(request.y), button=str(request.button or "left"))
        if request.action == "drag":
            return self._session.drag(int(request.x), int(request.y), int(request.to_x), int(request.to_y), button=str(request.button or "left"))
        if request.action == "scroll":
            direction = "down" if int(request.delta_y or 0) >= 0 else "up"
            clicks = max(1, abs(int(request.delta_y or request.delta_x or 1)))
            return self._session.scroll(int(request.x or 0), int(request.y or 0), direction=direction, clicks=clicks)
        if request.action == "type_text":
            return self._session.type(str(request.text or ""))
        if request.action == "key":
            return self._session.keypress(str(request.key or ""))
        return {"executed": False, "reason": "Unsupported desktop input action."}


def _unlink_capture_file(path: str) -> bool:
    if not path:
        return False
    try:
        capture_path = Path(path)
        existed = capture_path.exists()
        capture_path.unlink(missing_ok=True)
        return existed and not capture_path.exists()
    except OSError:
        return False
