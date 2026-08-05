"""Finite production backend for the Host Pack catalog read operation."""

from __future__ import annotations

from tobkiri_host.backends import (
    REQUIRED_PRODUCTION_GATES,
    BackendStatus,
)
from tobkiri_host.broker import RequestEnvelope
from tobkiri_host.contracts import ResolvedOperationBinding
from tobkiri_host.effects import ProviderOutcome
from tobkiri_host.models import ExecutionKind, OpaqueAuthorityRef, RuntimeEvidence

from .pack_control_v4 import (
    PACK_CONTROL_CONTRACT,
    CapturedPackCatalogReader,
    PackControlDenied,
)


PACK_CATALOG_BACKEND_ID = "tobkiri.python-host-v4"


class PackCatalogBackendV4:
    """Serve only the exact captured ``catalog.read`` Function principal."""

    def __init__(
        self,
        *,
        reader: CapturedPackCatalogReader,
        target_principal_id: str,
        implementation_digest: str,
        domain_id: str,
        backend_digest: str,
    ) -> None:
        self._reader = reader
        self._target_principal_id = target_principal_id
        self._implementation_digest = implementation_digest
        self._domain_id = domain_id
        self.status = BackendStatus(
            backend_id=PACK_CATALOG_BACKEND_ID,
            execution_kind=ExecutionKind.HOST_EXTENSION,
            platform="any-any",
            backend_digest=backend_digest,
            production_enabled=True,
            conformance_only=False,
            satisfied_gates=REQUIRED_PRODUCTION_GATES,
        )

    def materialize(
        self,
        binding: ResolvedOperationBinding,
        reservation_id: str,
    ) -> RuntimeEvidence:
        """Return Host evidence only for the pinned read-only Provider."""

        if (
            not reservation_id
            or binding.principal_ref.value != self._target_principal_id
            or binding.operation.contract_id != PACK_CONTROL_CONTRACT
            or binding.operation.operation_id != "catalog.read"
            or binding.function.implementation_digest != self._implementation_digest
        ):
            raise PackControlDenied("Pack catalog backend binding is unavailable")
        return RuntimeEvidence(
            domain_ref=OpaqueAuthorityRef(self._domain_id),
            executable_digest=self._implementation_digest,
            backend_digest=self.status.backend_digest,
            authenticated_channel=True,
            nonce_fresh=True,
        )

    def invoke(self, request: object) -> ProviderOutcome:
        """Read the catalog after exact Broker envelope validation."""

        if not isinstance(request, RequestEnvelope) or (
            request.target_principal.value != self._target_principal_id
            or request.target_domain.value != self._domain_id
            or request.contract_id != PACK_CONTROL_CONTRACT
            or request.operation_id != "catalog.read"
            or dict(request.payload)
        ):
            raise PackControlDenied("Pack catalog Provider envelope is invalid")
        return ProviderOutcome(self._reader.read())

    def cancel(self, request_id: str) -> None:
        """Accept cancellation without exposing another operation."""

        del request_id

    def terminate(self, domain_id: str) -> None:
        """Accept a Host fence only for this exact Provider domain."""

        if domain_id != self._domain_id:
            raise PackControlDenied("Pack catalog Provider domain is invalid")


__all__ = ["PACK_CATALOG_BACKEND_ID", "PackCatalogBackendV4"]
