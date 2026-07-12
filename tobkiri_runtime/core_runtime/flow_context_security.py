"""Helpers for separating user flow inputs from kernel-owned context keys."""
from __future__ import annotations

from typing import Any, Mapping

# Kernel-owned flow context keys/prefixes must never be supplied by a caller's
# input dictionary. Trusted runtime code should pass these values via the
# dedicated trusted_context argument on execute_flow()/execute_flow_sync().
RESERVED_FLOW_CONTEXT_KEYS: frozenset[str] = frozenset({
    "_principal_id",
    "_flow_run_principal_id",
    "_flow_run_request_id",
    "_flow_call_stack",
    "_flow_id",
    "_flow_execution_id",
    "_flow_timeout",
    "_flow_defaults",
    "_parent_flow_id",
    "_parent_flow",
    "_parent_flow_execution_id",
    "_current_step",
    "_total_steps",
})

RESERVED_FLOW_CONTEXT_PREFIXES: tuple[str, ...] = (
    "_flow_",
    "_kernel_",
    "_step_out.",
    "_flow_control",
    "_error",
)


def is_reserved_flow_context_key(key: str) -> bool:
    """Return True when *key* is owned by the flow runtime."""
    return key in RESERVED_FLOW_CONTEXT_KEYS or any(
        key.startswith(prefix) for prefix in RESERVED_FLOW_CONTEXT_PREFIXES
    )


def reserved_flow_context_keys(context: Mapping[str, Any] | None) -> list[str]:
    """List reserved keys present in a caller-supplied flow context."""
    if not isinstance(context, Mapping):
        return []
    return sorted(
        key for key in context.keys()
        if isinstance(key, str) and is_reserved_flow_context_key(key)
    )


def sanitize_user_flow_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy caller inputs while dropping kernel-owned flow context keys."""
    if not isinstance(context, Mapping):
        return {}
    return {
        key: value for key, value in context.items()
        if not (isinstance(key, str) and is_reserved_flow_context_key(key))
    }
