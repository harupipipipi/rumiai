from __future__ import annotations

import uuid
from typing import Callable

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
from ..providers.base import GuestAgentClient, ProgressSink
from .fake_guest_agent import FakeGuestAgent


class FakeRuntimeProvider:
    def __init__(
        self,
        *,
        provider_id: str = "fake",
        capabilities: frozenset[str] | set[str] | tuple[str, ...] = frozenset({"sandbox.exec"}),
        ready: bool = True,
        platform: str = "test",
        guest_agent: FakeGuestAgent | None = None,
        sandbox_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.capabilities = frozenset(capabilities)
        self.ready = ready
        self.platform = platform
        self.guest_agent = guest_agent or FakeGuestAgent()
        self.instances: dict[str, ProviderInstance] = {}
        self._sandbox_id_factory = sandbox_id_factory

    def doctor(self, request: RuntimeRequirements) -> RuntimeProviderStatus:
        missing = tuple(sorted(request.required_capabilities - self.capabilities))
        ready = self.ready and not missing
        return RuntimeProviderStatus(
            provider_id=self.provider_id,
            platform=self.platform,
            available=True,
            installed=True,
            ready=ready,
            version="fake-1",
            capabilities=self.capabilities,
            missing_requirements=missing,
            requires_user_action=False,
            user_action=None,
            reboot_required=False,
            diagnostics=()
            if ready
            else (Diagnostic(code="FAKE_PROVIDER_NOT_READY", message="Fake provider does not satisfy requirements"),),
        )

    def ensure(self, request: EnsureRuntimeRequest, progress: ProgressSink) -> OperationResult:
        progress.emit(ProgressEvent(operation_id="fake-ensure", stage="ready", message="Fake provider ready"))
        return OperationResult(ok=True, provider_id=self.provider_id, operation_id="fake-ensure", status="ready")

    def update(self, request: UpdateRuntimeRequest, progress: ProgressSink) -> OperationResult:
        progress.emit(ProgressEvent(operation_id="fake-update", stage="done", message="Fake provider updated"))
        return OperationResult(ok=True, provider_id=self.provider_id, operation_id="fake-update", status="updated")

    def uninstall(self, request: UninstallRuntimeRequest, progress: ProgressSink) -> OperationResult:
        progress.emit(ProgressEvent(operation_id="fake-uninstall", stage="done", message="Fake provider uninstalled"))
        self.instances.clear()
        return OperationResult(ok=True, provider_id=self.provider_id, operation_id="fake-uninstall", status="uninstalled")

    def create(self, spec: SandboxCreateSpec) -> ProviderInstance:
        sandbox_id = self._sandbox_id_factory() if self._sandbox_id_factory is not None else str(uuid.uuid4())
        instance = ProviderInstance(
            provider_id=self.provider_id,
            provider_instance_id=f"fake-{sandbox_id}",
            sandbox_id=sandbox_id,
            runtime_id="fake-runtime",
            state="stopped",
            opaque_state={"template_id": spec.template.template_id},
        )
        self.instances[instance.provider_instance_id] = instance
        return instance

    def start(self, instance: ProviderInstance) -> ProviderInstance:
        started = ProviderInstance(
            provider_id=instance.provider_id,
            provider_instance_id=instance.provider_instance_id,
            sandbox_id=instance.sandbox_id,
            runtime_id=instance.runtime_id,
            state="ready",
            opaque_state=instance.opaque_state,
            generation=instance.generation + 1,
        )
        self.instances[started.provider_instance_id] = started
        return started

    def stop(self, instance: ProviderInstance, *, force: bool = False) -> None:
        stopped = ProviderInstance(
            provider_id=instance.provider_id,
            provider_instance_id=instance.provider_instance_id,
            sandbox_id=instance.sandbox_id,
            runtime_id=instance.runtime_id,
            state="stopped",
            opaque_state={**instance.opaque_state, "force": force},
            generation=instance.generation + 1,
        )
        self.instances[stopped.provider_instance_id] = stopped

    def destroy(self, instance: ProviderInstance) -> None:
        self.instances.pop(instance.provider_instance_id, None)

    def reconcile(self, persisted: ProviderInstance) -> ReconcileResult:
        current = self.instances.get(persisted.provider_instance_id, persisted)
        return ReconcileResult(instance=current, changed=current != persisted)

    def connect_agent(self, instance: ProviderInstance) -> GuestAgentClient:
        return self.guest_agent
