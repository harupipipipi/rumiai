"""Execution selection and all-or-nothing production backend feature gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from .contracts import ResolvedOperationBinding
from .errors import BackendUnavailableError
from .models import ExecutionKind, RuntimeEvidence


REQUIRED_PRODUCTION_GATES = frozenset(
    {
        "artifact_verified",
        "static_admission",
        "security_epoch",
        "authority",
        "audit",
        "resource_controller",
        "runtime_evidence",
        "cancellation",
    }
)


@dataclass(frozen=True)
class BackendStatus:
    """Backend availability with independently verifiable safety gates."""

    backend_id: str
    execution_kind: ExecutionKind
    platform: str
    backend_digest: str
    production_enabled: bool = False
    conformance_only: bool = True
    satisfied_gates: frozenset[str] = frozenset()

    @property
    def ready_for_production(self) -> bool:
        """Return true only when the backend and every prerequisite are ready."""
        return (
            self.production_enabled
            and not self.conformance_only
            and REQUIRED_PRODUCTION_GATES <= self.satisfied_gates
        )


class ExecutionBackend(Protocol):
    """Common materialization and invocation supervisor interface."""

    status: BackendStatus

    def materialize(
        self,
        binding: ResolvedOperationBinding,
        reservation_id: str,
    ) -> RuntimeEvidence:
        """Start or reuse an exact workload and return Host-verified evidence."""

    def invoke(self, request: object) -> object:
        """Invoke through the authenticated backend channel."""

    def cancel(self, request_id: str) -> None:
        """Fence new I/O and terminate Host-owned local execution."""

    def terminate(self, domain_id: str) -> None:
        """Destroy a mismatched or revoked execution domain."""


class BackendRegistry:
    """Select exact backends without a weaker fallback."""

    def __init__(self, backends: Iterable[ExecutionBackend]) -> None:
        self._backends = {backend.status.backend_id: backend for backend in backends}

    def select(
        self,
        binding: ResolvedOperationBinding,
        *,
        production: bool = True,
    ) -> ExecutionBackend:
        """Select the variant-pinned backend and enforce its feature gates."""
        backend = self._backends.get(binding.variant.backend)
        if backend is None:
            raise BackendUnavailableError("pinned backend is not installed")
        status = backend.status
        if status.execution_kind is not binding.variant.execution_kind:
            raise BackendUnavailableError("backend execution kind mismatch")
        if production and not status.ready_for_production:
            missing = sorted(REQUIRED_PRODUCTION_GATES - status.satisfied_gates)
            raise BackendUnavailableError(
                f"backend is feature-disabled; missing gates: {missing}"
            )
        if not production and not (
            status.conformance_only or status.ready_for_production
        ):
            raise BackendUnavailableError("backend is disabled")
        return backend
