"""Deterministic AI gateway over manifest-selected global providers."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from core_runtime.global_contract_dispatch import (
    GlobalContractClient,
    GlobalContractInvocationError,
    GlobalContractUnavailable,
)

CATALOG_CONTRACT = "rumi.resource.ai.model.catalog.v1"
GENERATE_PROVIDER_CONTRACT = "rumi.service.ai.provider.generate.v1"
STREAM_PROVIDER_CONTRACT = "rumi.service.ai.provider.stream.v1"
HEALTH_CONTRACT = "rumi.resource.ai.provider.health.v1"
USAGE_CONTRACT = "rumi.service.ai.usage.cost.v1"
ROUTING_CONTRACT = "rumi.service.ai.route.v1"

_DIAGNOSTIC_LIMIT = 256
_DIAGNOSTICS: list[dict[str, Any]] = []
_DIAGNOSTIC_LOCK = threading.Lock()


@dataclass(frozen=True)
class RouteRequirement:
    """Provider-neutral request requirements bound to one route decision."""

    modalities: frozenset[str]
    capabilities: frozenset[str]
    tool_calling: bool
    thinking: bool
    minimum_context: int
    request_surface: str
    data_residency: str | None
    maximum_cost: float | None
    preferred_model_id: str | None
    preferred_provider_instance_id: str | None
    health_max_age: float


@dataclass(frozen=True)
class Candidate:
    """One catalog model joined to an executable selected provider handle."""

    model_id: str
    provider_instance_id: str
    catalog_provider_instance_id: str
    catalog_revision: str
    capabilities: frozenset[str]
    modalities: frozenset[str]
    context_length: int
    input_cost: float | None
    output_cost: float | None
    priority: int
    available: bool
    health: str
    health_observed_at: float | None
    raw: Mapping[str, Any]


def create_generate_operation(client: GlobalContractClient):
    """Create the global non-streaming gateway operation."""

    def operation(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if name not in {"generate", "invoke"}:
            raise ValueError(f"unknown generate operation: {name}")
        return _invoke(client, payload, streaming=False)

    return operation


def create_stream_operation(client: GlobalContractClient):
    """Create the global streaming gateway operation."""

    def operation(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if name not in {"stream", "invoke"}:
            raise ValueError(f"unknown stream operation: {name}")
        return _invoke(client, payload, streaming=True)

    return operation


def create_routing_diagnostics_operation(client: GlobalContractClient):
    """Create a redacted read-only routing diagnostic resource."""
    del client

    def operation(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if name not in {"list", "get"}:
            raise ValueError(f"unknown diagnostic operation: {name}")
        request_id = str(payload.get("request_id") or "").strip()
        with _DIAGNOSTIC_LOCK:
            values = [dict(item) for item in _DIAGNOSTICS]
        if request_id:
            values = [item for item in values if item["request_id"] == request_id]
        return {"diagnostics": values, "count": len(values)}

    return operation


def _invoke(
    client: GlobalContractClient,
    payload: Mapping[str, Any],
    *,
    streaming: bool,
) -> dict[str, Any]:
    request = dict(payload)
    request_id = str(request.get("request_id") or uuid.uuid4())
    deadline = _deadline(request)
    requirement = _requirement(request)
    provider_contract = (
        STREAM_PROVIDER_CONTRACT if streaming else GENERATE_PROVIDER_CONTRACT
    )
    provider_metadata = {
        str(item.get("provider_instance_id") or ""): item
        for item in client.providers(provider_contract)
    }
    if not provider_metadata:
        raise GlobalContractInvocationError(
            "missing_provider",
            f"no selected provider for {provider_contract}",
        )
    health = _health(client)
    candidates, excluded = _catalog_candidates(
        client,
        provider_metadata,
        requirement,
        health,
    )
    if not candidates:
        _record_diagnostic(
            request_id,
            requirement,
            (),
            excluded,
            selected=None,
            policy_revision=str(request.get("policy_revision") or ""),
        )
        raise GlobalContractInvocationError(
            "capability_mismatch",
            "no selected model satisfies the request requirements",
        )
    ordered = candidates
    selected = ordered[0]
    _record_diagnostic(
        request_id,
        requirement,
        candidates,
        excluded,
        selected=selected,
        policy_revision=str(request.get("policy_revision") or ""),
    )
    credential_handle = request.get("credential_handle")
    if credential_handle is not None and not str(credential_handle).startswith(
        ("credential:", "opaque:")
    ):
        raise GlobalContractInvocationError(
            "denied",
            "gateway accepts only opaque credential handles",
        )
    invocation = {
        "request_id": request_id,
        "model_id": str(
            selected.raw.get("provider_model_id") or selected.model_id
        ),
        "provider_id": str(selected.raw.get("provider_id") or ""),
        "messages": request.get("messages") or [],
        "input": request.get("input"),
        "parameters": dict(request.get("parameters") or {}),
        "tools": list(request.get("tools") or []),
        "required_capabilities": sorted(requirement.capabilities),
        "required_modalities": sorted(requirement.modalities),
        "request_surface": requirement.request_surface,
        "deadline": deadline,
        "credential_handle": credential_handle,
        "idempotency_key": request.get("idempotency_key"),
    }
    attempts: list[dict[str, Any]] = []
    allow_failover = bool(request.get("allow_failover", False))
    replay_safe = bool(request.get("idempotency_key")) and not invocation["tools"]
    for attempt_number, attempt_candidate in enumerate(ordered, 1):
        invocation["attempt"] = attempt_number
        invocation["model_id"] = str(
            attempt_candidate.raw.get("provider_model_id")
            or attempt_candidate.model_id
        )
        invocation["provider_id"] = str(
            attempt_candidate.raw.get("provider_id") or ""
        )
        try:
            value = client.invoke(
                provider_contract,
                "stream" if streaming else "generate",
                invocation,
                provider_instance_id=attempt_candidate.provider_instance_id,
            )
            if streaming:
                events = _normalize_stream(value, request_id)
                _attach_stream_usage_cost(client, events, attempt_candidate)
                return {
                    "request_id": request_id,
                    "model_id": attempt_candidate.model_id,
                    "provider_instance_id": attempt_candidate.provider_instance_id,
                    "events": events,
                    "attempts": attempts,
                }
            result = _normalize_result(value, request_id, attempt_candidate)
            result["usage_cost"] = _usage_cost(
                client,
                result["usage"],
                attempt_candidate,
                result["usage_provenance"],
            )
            result["attempts"] = attempts
            return result
        except GlobalContractUnavailable as exc:
            failure = GlobalContractInvocationError(
                "provider_unavailable",
                str(exc),
            )
        except GlobalContractInvocationError as exc:
            failure = exc
        attempts.append(
            {
                "attempt": attempt_number,
                "model_id": attempt_candidate.model_id,
                "provider_instance_id": attempt_candidate.provider_instance_id,
                "error_code": failure.code,
            }
        )
        retryable = failure.code in {
            "provider_unavailable",
            "quota",
            "invalid_response",
        }
        if (
            not allow_failover
            or not replay_safe
            or not retryable
            or attempt_number >= len(ordered)
        ):
            raise failure
    raise GlobalContractInvocationError(
        "provider_unavailable",
        "all selected providers failed",
    )


def _deadline(request: Mapping[str, Any]) -> float:
    now = time.time()
    raw = request.get("deadline")
    try:
        deadline = float(raw)
    except (TypeError, ValueError):
        deadline = now + 60.0
    if deadline <= now:
        raise GlobalContractInvocationError("deadline", "request deadline elapsed")
    return deadline


def _requirement(request: Mapping[str, Any]) -> RouteRequirement:
    requirement = request.get("requirements")
    requirement = requirement if isinstance(requirement, Mapping) else {}
    modalities = _strings(requirement.get("modalities")) or frozenset({"text"})
    maximum_cost = _optional_float(requirement.get("maximum_cost"))
    return RouteRequirement(
        modalities=modalities,
        capabilities=_strings(requirement.get("capabilities")),
        tool_calling=bool(requirement.get("tool_calling", False)),
        thinking=bool(requirement.get("thinking", False)),
        minimum_context=max(0, int(requirement.get("minimum_context") or 0)),
        request_surface=str(requirement.get("request_surface") or "chat"),
        data_residency=(
            str(requirement.get("data_residency"))
            if requirement.get("data_residency")
            else None
        ),
        maximum_cost=maximum_cost,
        preferred_model_id=(
            str(requirement.get("preferred_model_id"))
            if requirement.get("preferred_model_id")
            else None
        ),
        preferred_provider_instance_id=(
            str(requirement.get("preferred_provider_instance_id"))
            if requirement.get("preferred_provider_instance_id")
            else None
        ),
        health_max_age=max(
            0.0,
            _optional_float(requirement.get("health_max_age")) or 60.0,
        ),
    )


def _health(client: GlobalContractClient) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for provider in client.providers(HEALTH_CONTRACT):
        provider_id = str(provider.get("provider_instance_id") or "")
        try:
            result = client.invoke(
                HEALTH_CONTRACT,
                "get",
                {},
                provider_instance_id=provider_id,
            )
        except Exception:
            continue
        items = result.get("providers") if isinstance(result, Mapping) else None
        for item in items if isinstance(items, list) else []:
            if isinstance(item, Mapping) and item.get("provider_instance_id"):
                values[str(item["provider_instance_id"])] = dict(item)
    return values


def _catalog_candidates(
    client: GlobalContractClient,
    providers: Mapping[str, Mapping[str, Any]],
    requirement: RouteRequirement,
    health: Mapping[str, Mapping[str, Any]],
) -> tuple[list[Candidate], list[dict[str, str]]]:
    catalog_models: list[dict[str, Any]] = []
    for catalog_provider in client.providers(CATALOG_CONTRACT):
        catalog_provider_id = str(
            catalog_provider.get("provider_instance_id") or ""
        )
        result = client.invoke(
            CATALOG_CONTRACT,
            "list",
            {},
            provider_instance_id=catalog_provider_id,
        )
        raw_models = result.get("models") if isinstance(result, Mapping) else None
        for raw in raw_models if isinstance(raw_models, list) else []:
            if not isinstance(raw, Mapping):
                continue
            descriptor = dict(raw)
            descriptor["catalog_provider_instance_id"] = catalog_provider_id
            catalog_models.append(descriptor)
    routed = client.invoke(
        ROUTING_CONTRACT,
        "route",
        {
            "models": catalog_models,
            "execution_providers": list(providers.values()),
            "health": dict(health),
            "requirements": _requirement_payload(requirement),
            "decision_time": time.time(),
        },
    )
    values = routed.get("candidates") if isinstance(routed, Mapping) else None
    excluded = routed.get("excluded") if isinstance(routed, Mapping) else None
    values = values if isinstance(values, list) else []
    excluded = excluded if isinstance(excluded, list) else []
    return (
        [
            _candidate_from_route(item)
            for item in values
            if isinstance(item, Mapping)
        ],
        [
            dict(item)
            for item in excluded
            if isinstance(item, Mapping)
        ],
    )


def _requirement_payload(requirement: RouteRequirement) -> dict[str, Any]:
    return {
        "modalities": sorted(requirement.modalities),
        "capabilities": sorted(requirement.capabilities),
        "tool_calling": requirement.tool_calling,
        "thinking": requirement.thinking,
        "minimum_context": requirement.minimum_context,
        "request_surface": requirement.request_surface,
        "data_residency": requirement.data_residency,
        "maximum_cost": requirement.maximum_cost,
        "preferred_model_id": requirement.preferred_model_id,
        "preferred_provider_instance_id": (
            requirement.preferred_provider_instance_id
        ),
        "health_max_age": requirement.health_max_age,
    }


def _candidate_from_route(value: Mapping[str, Any]) -> Candidate:
    descriptor = value.get("descriptor")
    descriptor = descriptor if isinstance(descriptor, Mapping) else {}
    return Candidate(
        model_id=str(value.get("model_id") or ""),
        provider_instance_id=str(
            value.get("execution_provider_instance_id") or ""
        ),
        catalog_provider_instance_id=str(
            value.get("catalog_provider_instance_id") or ""
        ),
        catalog_revision=str(value.get("catalog_revision") or "unknown"),
        capabilities=frozenset(_strings(value.get("capabilities"))),
        modalities=frozenset(_strings(value.get("modalities"))),
        context_length=int(value.get("context_length") or 0),
        input_cost=_optional_float(value.get("input_cost")),
        output_cost=_optional_float(value.get("output_cost")),
        priority=int(value.get("priority") or 0),
        available=True,
        health=str(value.get("health") or "unknown"),
        health_observed_at=_optional_float(value.get("health_observed_at")),
        raw=dict(descriptor),
    )


def _normalize_result(
    value: Any,
    request_id: str,
    selected: Candidate,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GlobalContractInvocationError(
            "invalid_response",
            "provider result must be an object",
        )
    if value.get("status") not in {None, "ok"}:
        raise GlobalContractInvocationError(
            str(value.get("error_code") or "provider_unavailable"),
            str(value.get("message") or "provider failed"),
        )
    return {
        "status": "ok",
        "request_id": request_id,
        "model_id": selected.model_id,
        "provider_instance_id": selected.provider_instance_id,
        "output": value.get("output"),
        "tool_intents": list(value.get("tool_intents") or []),
        "finish_reason": str(value.get("finish_reason") or "stop"),
        "usage": dict(value.get("usage") or {}),
        "usage_provenance": str(
            value.get("usage_provenance") or "provider_reported"
        ),
    }


def _normalize_stream(value: Any, request_id: str) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        events = value.get("events")
    else:
        events = value
    if not isinstance(events, Iterable) or isinstance(events, (str, bytes, Mapping)):
        raise GlobalContractInvocationError(
            "invalid_response",
            "provider stream must contain iterable events",
        )
    normalized: list[dict[str, Any]] = []
    allowed_types = {
        "text_delta",
        "thinking_delta",
        "tool_intent_delta",
        "usage",
        "finish",
        "error",
    }
    for sequence, event in enumerate(events):
        if not isinstance(event, Mapping):
            raise GlobalContractInvocationError(
                "invalid_response",
                "stream event must be an object",
            )
        event_type = str(event.get("type") or "")
        if event_type not in allowed_types:
            raise GlobalContractInvocationError(
                "invalid_response",
                f"unknown stream event type: {event_type}",
            )
        normalized.append(
            {
                "request_id": request_id,
                "sequence": sequence,
                "type": event_type,
                "delta": event.get("delta"),
                "tool_intent": event.get("tool_intent"),
                "usage": event.get("usage"),
                "finish_reason": event.get("finish_reason"),
                "provider_attempt": 1,
            }
        )
    return normalized


def _attach_stream_usage_cost(
    client: GlobalContractClient,
    events: list[dict[str, Any]],
    candidate: Candidate,
) -> None:
    for event in events:
        usage = event.get("usage")
        if event.get("type") == "usage" and isinstance(usage, Mapping):
            event["usage_cost"] = _usage_cost(
                client,
                usage,
                candidate,
                "provider_reported",
            )


def _usage_cost(
    client: GlobalContractClient,
    usage: Mapping[str, Any],
    candidate: Candidate,
    provenance: str,
) -> dict[str, Any]:
    return client.invoke(
        USAGE_CONTRACT,
        "calculate",
        {
            "usage": dict(usage),
            "usage_provenance": provenance,
            "pricing": {
                "input": candidate.input_cost,
                "output": candidate.output_cost,
                "currency": str(candidate.raw.get("currency") or "USD"),
            },
            "pricing_revision": candidate.catalog_revision,
        },
    )


def _record_diagnostic(
    request_id: str,
    requirement: RouteRequirement,
    candidates: Iterable[Candidate],
    excluded: list[dict[str, str]],
    *,
    selected: Candidate | None,
    policy_revision: str,
) -> None:
    record = {
        "request_id": request_id,
        "created_at": time.time(),
        "requirements": {
            "modalities": sorted(requirement.modalities),
            "capabilities": sorted(requirement.capabilities),
            "tool_calling": requirement.tool_calling,
            "thinking": requirement.thinking,
            "minimum_context": requirement.minimum_context,
            "request_surface": requirement.request_surface,
            "data_residency": requirement.data_residency,
            "maximum_cost": requirement.maximum_cost,
            "health_max_age": requirement.health_max_age,
        },
        "candidates": [
            {
                "model_id": item.model_id,
                "provider_instance_id": item.provider_instance_id,
                "catalog_revision": item.catalog_revision,
                "health": item.health,
                "health_observed_at": item.health_observed_at,
            }
            for item in candidates
        ],
        "excluded": list(excluded),
        "selected": (
            {
                "model_id": selected.model_id,
                "provider_instance_id": selected.provider_instance_id,
                "catalog_revision": selected.catalog_revision,
            }
            if selected is not None
            else None
        ),
        "policy_revision": policy_revision,
    }
    with _DIAGNOSTIC_LOCK:
        _DIAGNOSTICS.append(record)
        del _DIAGNOSTICS[:-_DIAGNOSTIC_LIMIT]


def _strings(value: Any) -> frozenset[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(str(item).strip() for item in value if str(item).strip())


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
