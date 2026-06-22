from __future__ import annotations

from typing import Any

from ._agent_os_common import err
from .sandbox_tools import _require_server_side_approval


def desktop_list(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del arguments, context
    return _sandbox_api().run({"_handler": "desktops_list"}, {})


def desktop_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    approval_error = _require_server_side_approval(context)
    if approval_error is not None:
        return approval_error
    payload = dict(arguments or {})
    _default_owner(payload, context)
    payload["_handler"] = "desktops_create"
    return _sandbox_api().run(payload, context or {})


def desktop_input(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    approval_error = _require_server_side_approval(context)
    if approval_error is not None:
        return approval_error
    payload = dict(arguments or {})
    seat_id = str(payload.get("seat_id") or payload.get("desktop_id") or "").strip()
    if not seat_id:
        return err("'seat_id' is required", "INVALID_INPUT")
    payload["seat_id"] = seat_id
    _default_owner(payload, context)
    _default_agent(payload, context)
    payload["_handler"] = "desktop_ai_input"
    return _sandbox_api().run(payload, context or {})


def desktop_rules_update(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    approval_error = _require_server_side_approval(context)
    if approval_error is not None:
        return approval_error
    payload = dict(arguments or {})
    seat_id = str(payload.get("seat_id") or payload.get("desktop_id") or "").strip()
    if not seat_id:
        return err("'seat_id' is required", "INVALID_INPUT")
    payload["seat_id"] = seat_id
    _default_owner(payload, context)
    payload["_handler"] = "desktop_rules_update"
    return _sandbox_api().run(payload, context or {})


def desktop_access_request(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(arguments or {})
    seat_id = str(payload.get("seat_id") or payload.get("desktop_id") or "").strip()
    if not seat_id:
        return err("'seat_id' is required", "INVALID_INPUT")
    payload["seat_id"] = seat_id
    _default_owner(payload, context)
    payload["_handler"] = "desktop_access_request"
    return _sandbox_api().run(payload, context or {})


def _default_owner(payload: dict[str, Any], context: dict[str, Any] | None) -> None:
    if payload.get("owner_id") or payload.get("access_owner_id"):
        return
    access = payload.get("access") if isinstance(payload.get("access"), dict) else None
    if access and access.get("owner_id"):
        return
    context = context if isinstance(context, dict) else {}
    owner_id = str(
        context.get("agent_id")
        or context.get("actor_id")
        or context.get("user_id")
        or "local-agent"
    ).strip()
    payload["owner_id"] = owner_id[:160] or "local-agent"
    if access is not None:
        access.setdefault("owner_id", payload["owner_id"])


def _default_agent(payload: dict[str, Any], context: dict[str, Any] | None) -> None:
    if payload.get("agent_id") or payload.get("actor_agent_id"):
        return
    context = context if isinstance(context, dict) else {}
    agent_id = str(
        context.get("agent_id")
        or context.get("actor_id")
        or context.get("user_id")
        or ""
    ).strip()
    if agent_id:
        payload["agent_id"] = agent_id[:160]


def _sandbox_api():
    try:
        from ecosystem.defaultspack.blocks.sandbox import api
    except ModuleNotFoundError:
        from blocks.sandbox import api  # type: ignore
    return api
