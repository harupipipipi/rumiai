from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any

from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController
from ..tool_policy.internal_context import tool_server_approval_context_is_internal

from .viewer_broker_client import ViewerBrokerClient

_VIEWER_RECOVERY_MESSAGE = (
    "Rumi Viewer が未接続です。foreground/on-screen 操作は承認と Rumi Viewer 接続後に利用できます。"
    "承認してください。Rumi Viewer を起動または前面表示して必要なデスクトップ権限を許可するか、表/前面で作業しますか?"
)
_VIEWER_BROKER_PLATFORMS = frozenset({"Darwin", "Windows"})
_TARGET_SENSITIVE_COMPUTER_ACTIONS = frozenset(
    {
        "computer.type",
        "computer.key",
        "computer.scroll",
        "computer.click_text",
        "computer.semantic_action",
        "computer.pid_event",
        "computer.move",
        "computer.click",
        "computer.drag",
    }
)
_TARGET_SENSITIVE_READ_ACTIONS = frozenset(
    {"computer.screenshot", "computer.ocr", "computer.ax_tree"}
)
_DISPLAY_CAPTURE_TARGETS = frozenset(
    {"primary_display", "all_displays", "screen", "display", "desktop"}
)
_EXACT_TARGET_SELECTION_REQUIRED = "EXACT_TARGET_SELECTION_REQUIRED"


def should_route_to_viewer(action: str) -> bool:
    if os.environ.get("RUMI_COMPUTER_HOST_INTERNAL") == "1":
        return False
    if platform.system() not in _VIEWER_BROKER_PLATFORMS:
        return False
    return str(action or "").startswith("computer.")


def run_computer_action(
    action: str,
    payload: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    *,
    tool_name: str = "computer_use",
    tool_arguments: dict[str, Any] | None = None,
    artifact_root: Path | None = None,
    yolo_mode: bool = False,
    controller_cls: type[Any] | None = None,
) -> dict[str, Any]:
    normalized_action = str(action or "")
    normalized_payload = dict(payload or {})
    normalized_context = dict(context or {}) if isinstance(context, dict) else {}
    if not _approval_token_present(normalized_payload):
        approval_token = _approval_token_from_context(normalized_context, tool_name, normalized_action)
        if approval_token:
            normalized_payload["approval_token"] = approval_token
    effective_yolo_mode = bool(yolo_mode) or _context_has_server_approval(normalized_context)
    if should_route_to_viewer(normalized_action):
        if _requires_target_binding(normalized_action, normalized_payload):
            normalized_payload, target_error = _materialize_persisted_target_window(
                normalized_action,
                normalized_payload,
                artifact_root=artifact_root,
            )
            if target_error is not None:
                return target_error
        client = ViewerBrokerClient.from_environment()
        if client.available():
            try:
                result = client.run_computer(
                    normalized_action,
                    normalized_payload,
                    context=normalized_context,
                    artifact_root=artifact_root,
                )
                if not isinstance(result, dict):
                    return {"action": normalized_action, "result": result}
                if _is_request_approval_needed(result):
                    return _approval_required_response(
                        tool_name,
                        str(result.get("action") or normalized_action),
                        normalized_payload,
                        result,
                        normalized_context,
                    )
                return _with_browser_text_input_recommendations(normalized_action, dict(result))
            except Exception as exc:
                return _viewer_connection_required_response(
                    normalized_action,
                    f"Rumi Viewer host broker is unavailable: {exc}",
                )
        return _viewer_connection_required_response(
            normalized_action,
            "Rumi Viewer is required for computer control on this desktop platform.",
        )
    return _run_local_controller(
        normalized_action,
        normalized_payload,
        tool_name=tool_name,
        tool_arguments=tool_arguments,
        artifact_root=artifact_root,
        yolo_mode=effective_yolo_mode,
        context=normalized_context,
        controller_cls=controller_cls,
    )


def _run_local_controller(
    action: str,
    payload: dict[str, Any],
    *,
    tool_name: str,
    tool_arguments: dict[str, Any] | None,
    artifact_root: Path | None,
    yolo_mode: bool,
    context: dict[str, Any] | None,
    controller_cls: type[Any] | None = None,
) -> dict[str, Any]:
    controller_type = controller_cls or BrowserComputerController
    result = controller_type(artifact_root=artifact_root).run(
        action,
        payload,
        yolo_mode=yolo_mode,
    )
    if not isinstance(result, dict):
        return {"action": action, "result": result}
    if _is_request_approval_needed(result):
        approval_payload = result.get("payload") if isinstance(result.get("payload"), dict) else payload
        return _approval_required_response(
            tool_name,
            str(result.get("action") or action),
            dict(approval_payload),
            result,
            context,
        )
    return dict(result)


def _requires_target_binding(action: str, payload: dict[str, Any]) -> bool:
    """Return whether a Viewer approval must be bound to one exact persisted target.

    Viewer does not trust a caller-provided yolo flag.  Every target-sensitive
    operation must reach the broker with a self-contained exact target.
    """
    if action in _TARGET_SENSITIVE_COMPUTER_ACTIONS:
        return True
    if action not in _TARGET_SENSITIVE_READ_ACTIONS:
        return False
    capture_target = str(payload.get("target") or payload.get("capture_target") or "").strip().lower()
    return capture_target not in _DISPLAY_CAPTURE_TARGETS


def _materialize_persisted_target_window(
    action: str,
    payload: dict[str, Any],
    *,
    artifact_root: Path | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Add the selected target to an approval payload without touching the desktop.

    This only reads BrowserComputerController's persisted computer.target_window
    state.  It must not enumerate windows, inspect the foreground app, or focus
    anything while an approval is being prepared.
    """
    if _has_exact_target_binding(payload):
        return payload, None
    target = _persisted_target_window(artifact_root=artifact_root)
    bound_target = _exact_target_window_mapping(target)
    if bound_target is not None and _target_matches_explicit_filters(bound_target, target, payload):
        materialized = dict(payload)
        materialized["window"] = bound_target
        return materialized, None
    return payload, _exact_target_selection_required_response(action)


def _persisted_target_window(*, artifact_root: Path | None) -> dict[str, Any] | None:
    try:
        state = BrowserComputerController(artifact_root=artifact_root)._computer_state()
    except Exception:
        return None
    target = state.get("target_window") if isinstance(state, dict) else None
    return dict(target) if isinstance(target, dict) else None


def _has_exact_target_binding(payload: dict[str, Any]) -> bool:
    window = payload.get("window")
    return _is_exact_target_window(window) or _is_exact_target_window(payload)


def _exact_target_window_mapping(target: dict[str, Any] | None) -> dict[str, Any] | None:
    if not _is_exact_target_window(target, require_usable=True):
        return None
    assert isinstance(target, dict)
    window_id = _positive_integer(target.get("window_id"))
    if window_id is None:
        window_id = _positive_integer(target.get("id"))
    if window_id is None:
        window_id = _positive_integer(target.get("hwnd"))
    if window_id is None:
        return None
    return {
        "app": str(target.get("app") or "").strip(),
        "pid": _positive_integer(target.get("pid")),
        "window_id": window_id,
        "x": _integer(target.get("x")),
        "y": _integer(target.get("y")),
        "width": _positive_integer(target.get("width")),
        "height": _positive_integer(target.get("height")),
    }


def _is_exact_target_window(value: Any, *, require_usable: bool = False) -> bool:
    if not isinstance(value, dict):
        return False
    app = str(value.get("app") or "").strip()
    window_id = _positive_integer(value.get("window_id"))
    if window_id is None:
        window_id = _positive_integer(value.get("id"))
    if window_id is None:
        window_id = _positive_integer(value.get("hwnd"))
    width = _positive_integer(value.get("width"))
    height = _positive_integer(value.get("height"))
    if not (
        app
        and _positive_integer(value.get("pid")) is not None
        and window_id is not None
        and _integer(value.get("x")) is not None
        and _integer(value.get("y")) is not None
        and width is not None
        and height is not None
    ):
        return False
    return not require_usable or (width >= 200 and height >= 120)


def _target_matches_explicit_filters(
    bound_target: dict[str, Any],
    persisted_target: dict[str, Any] | None,
    payload: dict[str, Any],
) -> bool:
    for source in (payload, payload.get("window")):
        if not isinstance(source, dict):
            continue
        app = str(source.get("app") or source.get("application") or source.get("process") or "").strip()
        if app and not _app_names_match(app, bound_target["app"]):
            return False
        title = str(
            source.get("title") or source.get("window_title") or source.get("title_contains") or ""
        ).strip()
        persisted_title = str((persisted_target or {}).get("title") or "").strip()
        if title and title.casefold() not in persisted_title.casefold():
            return False
        if not _optional_target_identifier_matches(source.get("pid"), bound_target["pid"]):
            return False
        wanted_window_id = source.get("window_id")
        if wanted_window_id in (None, ""):
            wanted_window_id = source.get("id")
        if not _optional_target_identifier_matches(wanted_window_id, bound_target["window_id"]):
            return False
        wanted_hwnd = _positive_integer(source.get("hwnd"))
        persisted_hwnd = _positive_integer((persisted_target or {}).get("hwnd"))
        if wanted_hwnd is not None and wanted_hwnd != persisted_hwnd:
            return False
        if source is not payload:
            for key in ("x", "y", "width", "height"):
                value = _integer(source.get(key))
                if value is not None and value != bound_target[key]:
                    return False
    return True


def _optional_target_identifier_matches(value: Any, expected: int) -> bool:
    parsed = _positive_integer(value)
    return parsed is None or parsed == expected


def _app_names_match(expected: str, actual: str) -> bool:
    expected_aliases = BrowserComputerController._app_alias_tokens(expected)
    actual_aliases = BrowserComputerController._app_alias_tokens(actual)
    return bool(expected_aliases and actual_aliases and expected_aliases.intersection(actual_aliases))


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else None


def _positive_integer(value: Any) -> int | None:
    number = _integer(value)
    return number if number is not None and number > 0 else None


def _exact_target_selection_required_response(action: str) -> dict[str, Any]:
    message = "Select an exact target window before approving this computer action."
    return {
        "action": action,
        "is_error": True,
        "error_code": _EXACT_TARGET_SELECTION_REQUIRED,
        "reason": message,
        "message": message,
        "user_prompt": "先に対象ウィンドウを正確に選択してください。",
        "recovery": {
            "kind": "exact_target_selection_required",
            "requires_target_selection": True,
            "prompt": "computer.select_window で対象ウィンドウを正確に選択してください。",
            "recommended_next_actions": ["computer.select_window"],
        },
        "permission_subject": "Rumi Viewer",
    }


def _approval_token_present(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(str(payload.get("approval_token") or "").strip())


def _with_browser_text_input_recommendations(action: str, result: dict[str, Any]) -> dict[str, Any]:
    normalized_action = str(result.get("action") or action or "").strip()
    result.setdefault("action", normalized_action)
    pending_approval = bool(result.get("requires_approval") or result.get("approval_required"))
    if normalized_action in {"computer.observe", "computer.screenshot"} and not (
        result.get("is_error") or pending_approval
    ):
        BrowserComputerController._with_browser_text_input_recommendations(result)
    return result


def _viewer_connection_required_response(action: str, reason: str) -> dict[str, Any]:
    return {
        "action": action,
        "is_error": True,
        "reason": reason,
        "message": _VIEWER_RECOVERY_MESSAGE,
        "user_prompt": _VIEWER_RECOVERY_MESSAGE,
        "recovery": {
            "kind": "viewer_connection_required",
            "requires_approval": True,
            "requires_viewer_connection": True,
            "prompt": _VIEWER_RECOVERY_MESSAGE,
            "note": (
                "Open Rumi Viewer and approve the request; foreground/on-screen operation is "
                "available after a connected Rumi Viewer has the required desktop permissions."
            ),
            "recommended_next_actions": [
                "approve_request",
                "open_rumi_viewer",
                "choose_foreground_work",
            ],
        },
        "permission_subject": "Rumi Viewer",
    }


def _approval_token_from_context(
    context: dict[str, Any] | None,
    tool_name: str,
    action: str,
) -> str:
    if not isinstance(context, dict):
        return ""
    tokens = context.get("tool_approval_tokens")
    if not isinstance(tokens, dict):
        return ""
    for key in (str(tool_name or "").strip(), str(action or "").strip()):
        token = str(tokens.get(key) or "").strip()
        if token:
            return token
    return ""


def _context_has_server_approval(context: dict[str, Any] | None) -> bool:
    if not isinstance(context, dict):
        return False
    return tool_server_approval_context_is_internal(context) or _context_has_verified_server_approval_token(context)


def _context_has_verified_server_approval_token(context: dict[str, Any]) -> bool:
    token = str(context.get("_tool_server_approval_token") or "").strip()
    operation = str(context.get("_tool_server_approval_operation") or "").strip()
    args_hash = str(context.get("_tool_server_approval_args_hash") or "").strip()
    if not token or not operation or not args_hash:
        return False
    pack_id = str(context.get("_tool_server_approval_pack_id") or "").strip()
    conversation_id = str(context.get("_tool_server_approval_conversation_id") or "").strip()
    for approval in _approval_modules():
        try:
            verification = approval.verify_execution_token(
                token,
                operation,
                args_hash,
                consume=False,
                pack_id=pack_id,
                conversation_id=conversation_id,
            )
        except Exception:
            continue
        if bool(getattr(verification, "valid", False)):
            return True
    return False


def _context_value(context: dict[str, Any] | None, *keys: str) -> str:
    if not isinstance(context, dict):
        return ""
    for key in keys:
        value = str(context.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_request_approval_needed(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    if not bool(result.get("requires_approval") or result.get("approval_required")):
        return False
    return not str(result.get("approval_request_id") or result.get("request_id") or "").strip()


def _approval_required_response(
    tool_name: str,
    action: str,
    payload: dict[str, Any],
    result: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if str(result.get("approval_request_id") or result.get("request_id") or "").strip():
        return result
    approval = _approval_module()

    safe_tool_name = str(tool_name or "computer_use").strip() or "computer_use"
    safe_action = str(action or safe_tool_name)
    request_arguments = _request_arguments(safe_tool_name, safe_action, payload)
    pack_id = _context_value(context, "owner_pack", "pack_id", "_source_pack_id") or "defaultspack"
    conversation_id = _context_value(context, "conversation_id", "conversation_turn_id")
    request = approval.create_approval_request(
        safe_action,
        "high",
        request_arguments,
        details={
            "tool_name": safe_tool_name,
            "action": safe_action,
            "function_id": safe_action,
            "arguments": dict(request_arguments or {}),
            "payload": dict(payload or {}),
            "pack_id": pack_id,
            "conversation_id": conversation_id,
            "permission_subject": "Rumi Viewer",
        },
    )
    wrapped = dict(result)
    wrapped.pop("approval_token", None)
    wrapped.update(
        {
            "action": safe_action,
            "tool_name": safe_tool_name,
            "operation": safe_action,
            "payload": dict(payload or {}),
            "requires_approval": True,
            "approval_required": True,
            "approval_request_id": request["request_id"],
            "request_id": request["request_id"],
            "risk_level": request.get("risk_level", "high"),
            "args_hash": request.get("args_hash"),
            "expires_at": request.get("expires_at"),
            "display_summary": request.get("display_summary") or safe_action,
            "permission_subject": "Rumi Viewer",
        }
    )
    if not wrapped.get("message") and wrapped.get("approval_hint"):
        wrapped["message"] = wrapped.get("approval_hint")
    wrapped.setdefault("user_prompt", "承認してください")
    wrapped.setdefault("message", "承認してください。表/前面で作業しますか?")
    if isinstance(wrapped.get("recovery"), dict):
        wrapped["recovery"].setdefault("prompt", wrapped["user_prompt"])
    warning = result.get("approval_warning")
    if isinstance(warning, str) and warning.strip():
        wrapped["approval_warning"] = warning
    expires_in = result.get("approval_expires_in_seconds")
    if expires_in is not None:
        wrapped["approval_expires_in_seconds"] = expires_in
    return wrapped


def _request_arguments(tool_name: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"action": action, "payload": dict(payload or {})}


def _approval_module():
    from ..safety import approval

    return approval


def _approval_modules() -> list[Any]:
    modules: list[Any] = []
    for import_name in (
        "ecosystem.defaultspack.domain.safety.approval",
        "domain.safety.approval",
    ):
        try:
            module = __import__(import_name, fromlist=["approval"])
        except Exception:
            continue
        if module not in modules:
            modules.append(module)
    if not modules:
        try:
            modules.append(_approval_module())
        except Exception:
            pass
    return modules


sys.modules.setdefault("domain.host_bridge.computer_router", sys.modules[__name__])
sys.modules.setdefault("ecosystem.defaultspack.domain.host_bridge.computer_router", sys.modules[__name__])
for _parent_name in ("domain.host_bridge", "ecosystem.defaultspack.domain.host_bridge"):
    _parent = sys.modules.get(_parent_name)
    if _parent is not None:
        setattr(_parent, "computer_router", sys.modules[__name__])
