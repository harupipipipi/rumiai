"""Canonical Pack v4 entrypoint for one conversation completion operation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def invoke(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one validated completion request through the canonical gateway."""
    if not isinstance(payload, Mapping):
        raise TypeError("conversation completion payload must be an object")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array")
    if any(not isinstance(item, Mapping) for item in messages):
        raise ValueError("every message must be an object")

    from ecosystem.defaultspack.domain.ai_client.gateway import LLMGateway

    result = LLMGateway(v4_authority_admitted=True).complete(dict(payload))
    if not isinstance(result, Mapping):
        raise RuntimeError("conversation Provider returned a non-object result")
    return dict(result)


__all__ = ["invoke"]
