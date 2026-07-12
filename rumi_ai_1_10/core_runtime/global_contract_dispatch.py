"""Generic dispatch from legacy host adapters to activated global providers."""

from __future__ import annotations

from typing import Any, Mapping

from .interface_registry import InterfaceRegistry
from .resolved_profile_scope import active_resolved_profile


class GlobalContractUnavailable(RuntimeError):
    """Raised when no unique active provider exists in the resolved plan."""


class GlobalContractInvocationError(RuntimeError):
    """Preserve a provider-neutral operation failure code across isolation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def invoke_global_contract(
    interface_registry: InterfaceRegistry,
    contract_id: str,
    operation: str,
    payload: Mapping[str, Any],
) -> Any:
    """Invoke one activated provider without branching on an implementation pack."""
    plan = active_resolved_profile()
    if plan is None:
        raise GlobalContractUnavailable("resolved profile is not active")
    key = f"global_contract.provider.{contract_id}"
    candidates = interface_registry.get(key, strategy="all")
    selected = {
        (
            item.source_pack_id,
            item.provider_instance_id,
            item.content_hash,
        )
        for item in plan.providers
        if item.contract_id == contract_id
    }
    eligible = []
    denied = 0
    for candidate in candidates if isinstance(candidates, list) else []:
        if not isinstance(candidate, dict):
            continue
        source_pack_id = str(candidate.get("source_pack_id") or "").strip()
        if source_pack_id not in plan.effective_pack_set:
            continue
        if str(candidate.get("contract_id") or "") != contract_id:
            continue
        identity = (
            source_pack_id,
            str(candidate.get("provider_instance_id") or ""),
            str(candidate.get("content_hash") or ""),
        )
        if identity not in selected:
            continue
        required_capabilities = {
            str(value)
            for value in candidate.get("required_capabilities", [])
            if str(value)
        }
        if not required_capabilities.issubset(
            set(plan.effective_permissions)
        ):
            denied += 1
            continue
        operation_handler = candidate.get("operation")
        if callable(operation_handler):
            eligible.append(candidate)
    eligible.sort(
        key=lambda item: (
            str(item.get("provider_instance_id") or ""),
            str(item.get("content_hash") or ""),
        )
    )
    if not eligible and denied:
        raise GlobalContractInvocationError(
            "denied",
            f"active profile does not grant {contract_id}",
        )
    if len(eligible) != 1:
        raise GlobalContractUnavailable(
            f"expected one active provider for {contract_id}; found {len(eligible)}"
        )
    return eligible[0]["operation"](operation, dict(payload))
