"""Validation for HostIntent JSON returned by ordinary pack functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core_runtime.host_permissions import get_host_permission_definition

from .models import HOST_INTENT_TYPES, HostIntent


@dataclass(frozen=True)
class HostIntentValidationResult:
    ok: bool
    intent: HostIntent | None = None
    errors: list[str] = field(default_factory=list)


def validate_host_intent(
    payload: dict[str, Any],
    *,
    caller_pack_id: str,
    caller_function_id: str,
    conversation_id: str = "",
) -> HostIntentValidationResult:
    if not isinstance(payload, dict):
        return HostIntentValidationResult(False, errors=["host intent must be an object"])
    intent = HostIntent.from_payload(
        payload,
        caller_pack_id=caller_pack_id,
        caller_function_id=caller_function_id,
        conversation_id=conversation_id,
    )
    errors: list[str] = []
    raw_caller = payload.get("caller")
    if isinstance(raw_caller, dict):
        supplied_pack_id = str(raw_caller.get("pack_id") or "").strip()
        supplied_function_id = str(raw_caller.get("function_id") or "").strip()
        expected_pack_id = str(caller_pack_id or "").strip()
        expected_function_id = str(caller_function_id or "").strip()
        if supplied_pack_id and expected_pack_id and supplied_pack_id != expected_pack_id:
            errors.append("caller pack id does not match execution context")
        if supplied_function_id and expected_function_id and supplied_function_id != expected_function_id:
            errors.append("caller function id does not match execution context")
    supplied_conversation_id = str(payload.get("conversation_id") or "").strip()
    expected_conversation_id = str(conversation_id or "").strip()
    if supplied_conversation_id:
        if not expected_conversation_id:
            errors.append("conversation id requires trusted execution context")
        elif supplied_conversation_id != expected_conversation_id:
            errors.append("conversation id does not match execution context")
    if intent.type not in HOST_INTENT_TYPES:
        errors.append("host intent type is invalid")
    definition = get_host_permission_definition(intent.operation)
    if definition is None:
        errors.append(f"unknown host operation: {intent.operation}")
    if not intent.caller_pack_id:
        errors.append("caller pack id is required")
    if not intent.caller_function_id:
        errors.append("caller function id is required")
    if definition is not None and intent.is_stream and not definition.stream_allowed:
        errors.append(f"operation does not allow streams: {intent.operation}")
    if definition is not None:
        duration = _duration_ms(intent.args, intent.stream)
        hard_limit = definition.max_duration_ms_hard
        if hard_limit is not None and duration is not None and duration > hard_limit:
            errors.append(f"duration exceeds hard limit: {duration}>{hard_limit}")
    return HostIntentValidationResult(not errors, intent=None if errors else intent, errors=errors)


def _duration_ms(args: dict[str, Any], stream: dict[str, Any]) -> int | None:
    for key in ("duration_ms", "max_duration_ms"):
        value = args.get(key)
        if value is None:
            value = stream.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        return parsed
    return None
