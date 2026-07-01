from __future__ import annotations

from typing import Any


def run_host_mediator(
    context: dict[str, Any] | None,
    args: dict[str, Any] | None,
    *,
    function_id: str,
    operation: str,
    stream_allowed: bool,
) -> dict[str, Any]:
    """Return a typed HostIntent for the core runtime to approve and broker.

    These functions intentionally do not touch host APIs. They are stable pack
    entrypoints whose output is routed through HostIntent validation, Authority,
    and the Viewer host broker.
    """

    normalized_args = dict(args or {}) if isinstance(args, dict) else {}
    normalized_context = dict(context or {}) if isinstance(context, dict) else {}
    stream_config = _stream_config(normalized_args, stream_allowed)
    intent_type = "host_stream_intent" if stream_config.get("enabled") else "host_intent"
    caller_pack_id = _first_string(
        normalized_context,
        "caller_pack_id",
        "owner_pack",
        "pack_id",
        "_source_pack_id",
    )
    caller_function_id = _first_string(
        normalized_context,
        "caller_function_id",
        "function_id",
        "_source_function_id",
    )
    return {
        "type": intent_type,
        "version": 1,
        "operation": operation,
        "args": _intent_args(normalized_args),
        "stream": stream_config,
        "reason": str(normalized_args.get("reason") or "").strip(),
        "caller": {
            "pack_id": caller_pack_id,
            "function_id": caller_function_id,
        },
        "conversation_id": _first_string(
            normalized_context,
            "conversation_id",
            "conversation_turn_id",
        ),
        "host_function_id": function_id,
    }


def _stream_config(args: dict[str, Any], stream_allowed: bool) -> dict[str, Any]:
    requested = args.get("stream")
    if isinstance(requested, dict):
        config = dict(requested)
    elif bool(requested):
        config = {"enabled": True}
    else:
        config = {}
    if config.get("enabled") and not stream_allowed:
        config["enabled"] = False
        config["rejected_reason"] = "operation_does_not_allow_stream"
    return config


def _intent_args(args: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in args.items()
        if key not in {"approval_token", "caller", "reason", "stream"}
    }


def _first_string(values: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(values.get(key) or "").strip()
        if value:
            return value
    return ""
