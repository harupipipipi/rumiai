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
    ordered = sorted(
        candidates,
        key=lambda item: _candidate_sort_key(item, requirement),
    )
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
        "model_id": selected.model_id,
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
        try:
            value = client.invoke(
                provider_contract,
                "stream" if streaming else "generate",
                invocation,
                provider_instance_id=attempt_candidate.provider_instance_id,
            )
            if streaming:
                events = _normalize_stream(value, request_id)
                return {
                    "request_id": request_id,
                    "model_id": attempt_candidate.model_id,
                    "provider_instance_id": attempt_candidate.provider_instance_id,
                    "events": events,
                    "attempts": attempts,
                }
            result = _normalize_result(value, request_id, attempt_candidate)
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
    candidates: list[Candidate] = []
    excluded: list[dict[str, str]] = []
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
        models = result.get("models") if isinstance(result, Mapping) else None
        for raw in models if isinstance(models, list) else []:
            if not isinstance(raw, Mapping):
                continue
            candidate, reason = _candidate(
                raw,
                catalog_provider_id,
                providers,
                requirement,
                health,
            )
            if candidate is None:
                excluded.append(
                    {
                        "model_id": str(raw.get("model_id") or "unknown"),
                        "reason": reason,
                    }
                )
            else:
                candidates.append(candidate)
    return candidates, excluded


def _candidate(
    raw: Mapping[str, Any],
    catalog_provider_id: str,
    providers: Mapping[str, Mapping[str, Any]],
    requirement: RouteRequirement,
    health: Mapping[str, Mapping[str, Any]],
) -> tuple[Candidate | None, str]:
    model_id = str(raw.get("model_id") or "").strip()
    provider_id = str(raw.get("execution_provider_instance_id") or "").strip()
    if not model_id or provider_id not in providers:
        return None, "execution_provider_unresolved"
    if raw.get("available", True) is False:
        return None, "model_unavailable"
    modalities = _strings(raw.get("modalities"))
    capabilities = _strings(raw.get("capabilities"))
    if not requirement.modalities.issubset(modalities):
        return None, "modality_mismatch"
    if requirement.tool_calling and "tool_calling" not in capabilities:
        return None, "tool_calling_mismatch"
    if requirement.thinking and "thinking" not in capabilities:
        return None, "thinking_mismatch"
    if not requirement.capabilities.issubset(capabilities):
        return None, "capability_mismatch"
    if int(raw.get("context_length") or 0) < requirement.minimum_context:
        return None, "context_length_mismatch"
    surfaces = _strings(raw.get("request_surfaces"))
    if surfaces and requirement.request_surface not in surfaces:
        return None, "request_surface_mismatch"
    residencies = _strings(raw.get("data_residency"))
    if requirement.data_residency and requirement.data_residency not in residencies:
        return None, "data_residency_mismatch"
    model_health = health.get(provider_id, {})
    health_status = str(model_health.get("status") or "unknown")
    observed_at = _optional_float(model_health.get("observed_at"))
    if (
        observed_at is not None
        and time.time() - observed_at > requirement.health_max_age
    ):
        health_status = "unknown"
    if health_status in {"unavailable", "denied", "invalid"}:
        return None, f"health_{health_status}"
    input_cost = _optional_float(raw.get("input_cost"))
    output_cost = _optional_float(raw.get("output_cost"))
    if requirement.maximum_cost is not None:
        cost = (input_cost or 0.0) + (output_cost or 0.0)
        if cost > requirement.maximum_cost:
            return None, "cost_policy_mismatch"
    return Candidate(
        model_id=model_id,
        provider_instance_id=provider_id,
        catalog_provider_instance_id=catalog_provider_id,
        catalog_revision=str(raw.get("catalog_revision") or "unknown"),
        capabilities=capabilities,
        modalities=modalities,
        context_length=int(raw.get("context_length") or 0),
        input_cost=input_cost,
        output_cost=output_cost,
        priority=int(raw.get("priority") or 0),
        available=bool(raw.get("available", True)),
        health=health_status,
        health_observed_at=observed_at,
        raw=dict(raw),
    ), ""


def _candidate_sort_key(
    candidate: Candidate,
    requirement: RouteRequirement,
) -> tuple[Any, ...]:
    preferred_provider = (
        0
        if requirement.preferred_provider_instance_id
        == candidate.provider_instance_id
        else 1
    )
    preferred_model = (
        0 if requirement.preferred_model_id == candidate.model_id else 1
    )
    health_order = {"healthy": 0, "degraded": 1, "unknown": 2}
    return (
        preferred_provider,
        preferred_model,
        health_order.get(candidate.health, 3),
        -candidate.priority,
        candidate.input_cost if candidate.input_cost is not None else float("inf"),
        candidate.output_cost if candidate.output_cost is not None else float("inf"),
        candidate.model_id,
        candidate.provider_instance_id,
        candidate.catalog_revision,
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
