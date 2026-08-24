"""Canonical Pack v4 conversation entrypoints."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from core_runtime.di_container import get_container
from core_runtime.global_contract_dispatch import (
    GlobalContractClient,
    GlobalContractUnavailable,
    captured_profile_id,
)

AI_GENERATE_CONTRACT = "tobkiri.service.ai.generate.v1"
AI_GENERATE_OPERATION = "rumi_ai_gateway_pack.ai-gateway.generate"
AI_STREAM_CONTRACT = "tobkiri.service.ai.stream.v1"
AI_STREAM_OPERATION = "rumi_ai_gateway_pack.ai-gateway.stream"
_AI_CONTRACTS = frozenset({AI_GENERATE_CONTRACT, AI_STREAM_CONTRACT})


def invoke(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Invoke canonical AI generation through the captured Host Broker."""
    request = _conversation_request(payload, surface="defaultspack.conversation")
    value = _client().invoke(
        AI_GENERATE_CONTRACT,
        AI_GENERATE_OPERATION,
        request,
    )
    if not isinstance(value, Mapping):
        raise RuntimeError("conversation Provider returned a non-object result")
    return _project_completion(value)


def stream(payload: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """Invoke canonical AI streaming through the captured Host Broker."""
    request = _conversation_request(
        payload,
        surface="defaultspack.conversation.stream",
    )
    value = _client().invoke(
        AI_STREAM_CONTRACT,
        AI_STREAM_OPERATION,
        request,
    )
    events = value.get("events") if isinstance(value, Mapping) else None
    if not isinstance(events, list):
        raise RuntimeError("conversation Provider returned an invalid stream")
    return iter(_project_stream(events))


def _client() -> GlobalContractClient:
    session = get_container().get_or_none("v4_dispatch_session")
    if session is None:
        raise GlobalContractUnavailable(
            "Pack v4 dispatch session is required for conversation"
        )
    return GlobalContractClient(
        session=session,
        allowed_contract_ids=_AI_CONTRACTS,
        consumer_pack_id="defaultspack",
    )


def _conversation_request(
    payload: Mapping[str, Any],
    *,
    surface: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("conversation payload must be an object")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array")
    if any(not isinstance(item, Mapping) for item in messages):
        raise ValueError("every message must be an object")
    request = dict(payload)
    session = get_container().get_or_none("v4_dispatch_session")
    if session is not None:
        request.setdefault("profile_id", captured_profile_id(session))
    requirements = request.get("requirements")
    requirements = dict(requirements) if isinstance(requirements, Mapping) else {}
    requirements["request_surface"] = surface
    request["requirements"] = requirements
    return request


def _project_completion(value: Mapping[str, Any]) -> dict[str, Any]:
    tool_intents = [
        dict(item)
        for item in value.get("tool_intents") or []
        if isinstance(item, Mapping)
    ]
    return {
        **dict(value),
        "content": _content_blocks(value.get("output"), tool_intents),
        "tool_calls": tool_intents,
    }


def _content_blocks(
    output: Any,
    tool_intents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if isinstance(output, list):
        blocks.extend(dict(item) for item in output if isinstance(item, Mapping))
    elif output not in {None, ""}:
        blocks.append({"type": "text", "text": str(output)})
    for intent in tool_intents:
        blocks.append(
            {
                "type": "tool_use",
                "id": str(intent.get("intent_id") or ""),
                "name": str(intent.get("operation") or ""),
                "input": dict(intent.get("arguments") or {}),
            }
        )
    return blocks


def _project_stream(events: list[Any]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    for item in events:
        if not isinstance(item, Mapping):
            continue
        event_type = str(item.get("type") or "")
        if event_type in {"text_delta", "thinking_delta"}:
            text = str(item.get("delta") or "")
            if text:
                projected.append(
                    {
                        "type": (
                            "content_delta"
                            if event_type == "text_delta"
                            else "reasoning_delta"
                        ),
                        "delta": {"type": "text", "text": text},
                    }
                )
        elif event_type == "tool_intent_delta":
            intent = item.get("tool_intent")
            if isinstance(intent, Mapping):
                projected.append(
                    {
                        "type": "tool_use",
                        "id": str(intent.get("intent_id") or ""),
                        "name": str(intent.get("operation") or ""),
                        "input": dict(intent.get("arguments") or {}),
                    }
                )
        elif event_type == "usage":
            if isinstance(item.get("usage"), Mapping):
                usage = dict(item["usage"])
                if isinstance(item.get("usage_cost"), Mapping):
                    usage["usage_cost"] = dict(item["usage_cost"])
        elif event_type == "finish":
            projected.append(
                {
                    "type": "stream_end",
                    "finish_reason": str(item.get("finish_reason") or "stop"),
                    "usage": usage,
                }
            )
        elif event_type == "error":
            projected.append(
                {
                    "type": "stream_end",
                    "finish_reason": "error",
                    "usage": usage,
                }
            )
    return projected


__all__ = [
    "AI_GENERATE_CONTRACT",
    "AI_GENERATE_OPERATION",
    "AI_STREAM_CONTRACT",
    "AI_STREAM_OPERATION",
    "invoke",
    "stream",
]
