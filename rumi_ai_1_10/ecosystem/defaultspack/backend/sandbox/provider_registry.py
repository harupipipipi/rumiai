from __future__ import annotations

from .errors import INVALID_PROVIDER_ID, RUNTIME_PROVIDER_UNAVAILABLE, SandboxContractError
from .models import RuntimeProviderStatus, RuntimeRequirements
from .policy import require_provider_id
from .providers.base import RuntimeProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, RuntimeProvider] = {}

    def register(self, provider: RuntimeProvider, *, replace: bool = False) -> None:
        provider_id = require_provider_id(provider.provider_id)
        if provider_id in self._providers and not replace:
            raise SandboxContractError(INVALID_PROVIDER_ID, f"Provider is already registered: {provider_id}", status_code=409)
        self._providers[provider_id] = provider

    def unregister(self, provider_id: str) -> None:
        self._providers.pop(require_provider_id(provider_id), None)

    def get(self, provider_id: str) -> RuntimeProvider:
        provider_id = require_provider_id(provider_id)
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise SandboxContractError(INVALID_PROVIDER_ID, f"Unknown runtime provider: {provider_id}", status_code=404) from exc

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def doctor(self, provider_id: str, request: RuntimeRequirements | None = None) -> RuntimeProviderStatus:
        return self.get(provider_id).doctor(request or RuntimeRequirements(provider_id=provider_id))

    def doctor_all(self, request: RuntimeRequirements | None = None) -> tuple[RuntimeProviderStatus, ...]:
        requirements = request or RuntimeRequirements()
        return tuple(provider.doctor(requirements) for provider in self._providers.values())

    def resolve(self, provider_id: str | None, request: RuntimeRequirements | None = None) -> RuntimeProvider:
        requirements = request or RuntimeRequirements(provider_id=provider_id)
        if provider_id and provider_id != "auto":
            provider = self.get(provider_id)
            status = provider.doctor(requirements)
            self._ensure_status_satisfies(status, requirements)
            return provider

        statuses = [(provider, provider.doctor(requirements)) for provider in self._providers.values()]
        for provider, status in statuses:
            if self._status_satisfies(status, requirements):
                return provider
        raise SandboxContractError(
            RUNTIME_PROVIDER_UNAVAILABLE,
            "No registered runtime provider satisfies the requested capabilities",
            status_code=503,
            details={
                "required_capabilities": sorted(requirements.required_capabilities),
                "providers": [status.provider_id for _, status in statuses],
            },
        )

    def _ensure_status_satisfies(self, status: RuntimeProviderStatus, request: RuntimeRequirements) -> None:
        if not self._status_satisfies(status, request):
            raise SandboxContractError(
                RUNTIME_PROVIDER_UNAVAILABLE,
                f"Runtime provider is not ready: {status.provider_id}",
                status_code=503,
                details={
                    "provider_id": status.provider_id,
                    "missing_requirements": list(status.missing_requirements),
                    "required_capabilities": sorted(request.required_capabilities),
                },
            )

    @staticmethod
    def _status_satisfies(status: RuntimeProviderStatus, request: RuntimeRequirements) -> bool:
        if not status.ready:
            return False
        if not request.required_capabilities.issubset(status.capabilities):
            return False
        return True
