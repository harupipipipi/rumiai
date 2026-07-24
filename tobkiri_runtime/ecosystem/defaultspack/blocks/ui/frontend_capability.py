"""Generic, profile-bound frontend contribution capability broker."""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from typing import Any

from blocks._common import error, ok
from core_runtime.frontend_host import build_frontend_catalog
from core_runtime.global_contract_dispatch import (
    GlobalContractInvocationError,
    GlobalContractUnavailable,
    invoke_global_contract,
)
from core_runtime.resolved_profile_scope import active_resolved_profile
from core_runtime.runtime_audit_helpers import audit_event

_REPLAY_LIMIT = 2048
_MAX_REQUEST_ID_LENGTH = 128
_MAX_CONTRACT_INPUT_BYTES = 64 * 1024
_SEEN_REQUESTS: OrderedDict[str, float] = OrderedDict()
_REPLAY_LOCK = threading.Lock()


def _consume_request(request_id: str, expires_at: float) -> bool:
    """Consume one short-lived request id and reject replay or expiry."""
    now = time.time()
    if (
        not request_id
        or len(request_id) > _MAX_REQUEST_ID_LENGTH
        or expires_at < now
        or expires_at > now + 60.0
    ):
        return False
    with _REPLAY_LOCK:
        expired = [key for key, value in _SEEN_REQUESTS.items() if value < now]
        for key in expired:
            _SEEN_REQUESTS.pop(key, None)
        if request_id in _SEEN_REQUESTS:
            return False
        _SEEN_REQUESTS[request_id] = expires_at
        while len(_SEEN_REQUESTS) > _REPLAY_LIMIT:
            _SEEN_REQUESTS.popitem(last=False)
    return True


def _declared_contracts(contribution: Any) -> set[str]:
    contracts: set[str] = set()
    for value in (
        contribution.action_contract,
        contribution.data_source_contract,
    ):
        if value:
            contracts.add(str(value))
    isolated = contribution.isolated
    if isinstance(isolated, dict):
        contracts.update(str(value) for value in isolated.get("rpc_contracts", []))
    return contracts


def _audit(
    context: dict,
    event_type: str,
    *,
    request_id: str,
    owner_pack_id: str,
    contribution_id: str,
    contract_id: str,
    operation: str = "",
    code: str = "",
) -> None:
    audit_event(
        context,
        event_type,
        {
            "request_id": request_id,
            "owner_pack_id": owner_pack_id,
            "contribution_id": contribution_id,
            "contract_id": contract_id,
            "operation": operation,
            **({"code": code} if code else {}),
        },
    )


def run(input_data: dict, context: dict) -> dict:
    """Invoke only a contract declared by the current verified contribution."""
    data = dict(input_data) if isinstance(input_data, dict) else {}
    plan = active_resolved_profile()
    registry = context.get("interface_registry") if isinstance(context, dict) else None
    if plan is None or registry is None:
        return error("Frontend capability is unavailable", "CAPABILITY_UNAVAILABLE")

    request_id = str(data.get("request_id") or "").strip()
    try:
        expires_at = float(data.get("expires_at") or 0)
    except (TypeError, ValueError):
        expires_at = 0
    if not _consume_request(request_id, expires_at):
        return error("Frontend capability request is stale", "STALE_OR_REPLAYED")

    plan_hash = str(data.get("plan_hash") or "").strip()
    profile_id = str(data.get("profile_id") or "").strip()
    owner_pack_id = str(data.get("owner_pack_id") or "").strip()
    contribution_id = str(data.get("contribution_id") or "").strip()
    contract_id = str(data.get("contract_id") or "").strip()
    if plan_hash != plan.plan_hash or profile_id != plan.profile_id:
        return error("Resolved frontend plan changed", "STALE_RESOLUTION")

    catalog = build_frontend_catalog(plan)
    matches = [
        item
        for item in catalog.contributions
        if item.contribution_id == contribution_id
        and item.owner_pack_id == owner_pack_id
        and item.resolved_plan_hash == plan_hash
    ]
    if len(matches) != 1 or contract_id not in _declared_contracts(matches[0]):
        _audit(
            context,
            "frontend_capability.denied",
            request_id=request_id,
            owner_pack_id=owner_pack_id,
            contribution_id=contribution_id,
            contract_id=contract_id,
            code="CAPABILITY_DENIED",
        )
        return error("Capability is not declared by this surface", "CAPABILITY_DENIED")
    if contract_id.startswith("rumi.action.") and context.get(
        "_tool_server_approved"
    ) is not True:
        _audit(
            context,
            "frontend_capability.denied",
            request_id=request_id,
            owner_pack_id=owner_pack_id,
            contribution_id=contribution_id,
            contract_id=contract_id,
            code="APPROVAL_REQUIRED",
        )
        return error("Capability action requires local approval", "CAPABILITY_DENIED")

    payload = data.get("payload")
    payload = dict(payload) if isinstance(payload, dict) else {}
    operation = str(payload.pop("operation", "")).strip()
    contract_input = payload.pop("input", payload)
    if (
        not operation
        or len(operation) > 160
        or not isinstance(contract_input, dict)
    ):
        return error("Capability request is invalid", "INVALID_CAPABILITY_REQUEST")
    contract_input = dict(contract_input)
    contract_input.setdefault("profile_id", profile_id)
    try:
        input_size = len(
            json.dumps(
                contract_input,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        input_size = _MAX_CONTRACT_INPUT_BYTES + 1
    if input_size > _MAX_CONTRACT_INPUT_BYTES:
        _audit(
            context,
            "frontend_capability.denied",
            request_id=request_id,
            owner_pack_id=owner_pack_id,
            contribution_id=contribution_id,
            contract_id=contract_id,
            operation=operation,
            code="CAPABILITY_INPUT_TOO_LARGE",
        )
        return error(
            "Capability input exceeds the registered transport limit",
            "CAPABILITY_INPUT_TOO_LARGE",
        )
    try:
        result = invoke_global_contract(
            registry,
            contract_id,
            operation,
            contract_input,
        )
        _audit(
            context,
            "frontend_capability.executed",
            request_id=request_id,
            owner_pack_id=owner_pack_id,
            contribution_id=contribution_id,
            contract_id=contract_id,
            operation=operation,
        )
        return ok(result)
    except GlobalContractUnavailable as exc:
        _audit(
            context,
            "frontend_capability.failed",
            request_id=request_id,
            owner_pack_id=owner_pack_id,
            contribution_id=contribution_id,
            contract_id=contract_id,
            operation=operation,
            code="CAPABILITY_UNAVAILABLE",
        )
        return error(str(exc), "CAPABILITY_UNAVAILABLE")
    except GlobalContractInvocationError as exc:
        _audit(
            context,
            "frontend_capability.failed",
            request_id=request_id,
            owner_pack_id=owner_pack_id,
            contribution_id=contribution_id,
            contract_id=contract_id,
            operation=operation,
            code=exc.code or "CAPABILITY_FAILED",
        )
        return error(str(exc), exc.code or "CAPABILITY_FAILED")
