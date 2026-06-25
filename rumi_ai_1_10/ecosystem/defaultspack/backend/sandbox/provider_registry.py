from __future__ import annotations

from typing import Protocol

from .errors import INVALID_PROVIDER_ID, RUNTIME_PROVIDER_UNAVAILABLE, SandboxContractError
from .models import RuntimeProviderStatus, RuntimeRequirements
from .policy import require_provider_id


class RuntimeProvider(Protocol):
    provider_id: str

    def doctor(self, request: RuntimeRequirements) -> RuntimeProviderStatus: ...


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, RuntimeProvider] = {}

    def register(self, provider: RuntimeProvider, *, replace: bool = False) -> None:
        provider_id = require_provider_id(provider.provider_id)
        if provider_id in self._providers and not replace:
            raise SandboxContractError(
                INVALID_PROVIDER_ID,
                f"Provider is already registered: {provider_id}",
                status_code=409,
            )
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> RuntimeProvider:
        provider_id = require_provider_id(provider_id)
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise SandboxContractError(
                INVALID_PROVIDER_ID,
                f"Unknown runtime provider: {provider_id}",
                status_code=404,
            ) from exc

    def resolve(
        self,
        provider_id: str | None,
        request: RuntimeRequirements,
    ) -> RuntimeProvider:
        if provider_id and provider_id != "auto":
            provider = self.get(provider_id)
            status = provider.doctor(request)
            if status.ready and request.required_capabilities.issubset(status.capabilities):
                return provider
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                f"Runtime provider is not ready: {provider_id}",
                status_code=503,
                details={"missing_requirements": list(status.missing_requirements)},
            )
        for provider in self._providers.values():
            status = provider.doctor(request)
            if status.ready and request.required_capabilities.issubset(status.capabilities):
                return provider
        raise SandboxContractError(
            RUNTIME_PROVIDER_UNAVAILABLE,
            "No registered runtime provider satisfies the requested capabilities",
            status_code=503,
            details={"required_capabilities": sorted(request.required_capabilities)},
        )
