from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result
from domain.tool.host_contract_adapter import run_host_contract_action


def run(context, args):
    """Run a browser/computer action through the reviewed host adapter."""

    args = dict(args or {})
    action = str(args.get("action", "browser.session"))
    payload = dict(args.get("payload") or {})
    tool_name = str(args.get("tool_name") or "browser_computer").strip()
    user_requested = bool(isinstance(context, dict) and context.get("user_requested_computer_use"))
    if user_requested and action == "browser.open_url" and not any(
        key in payload for key in ("persistent", "profile_id", "session_id")
    ):
        payload["persistent"] = False
    payload = _normalize_browser_open_url_payload(
        action,
        payload,
        args.get("tool_arguments"),
    )
    payload = _payload_with_context_defaults(action, payload, context)
    if action == "browser.download.collect" and isinstance(context, dict):
        workspace = str(context.get("conversation_workspace_dir") or "").strip()
        if workspace:
            payload["artifact_root"] = str(Path(workspace) / "tools" / "computer")
    runner = _run_computer_action()
    result = runner(
        action,
        payload,
        context if isinstance(context, dict) else None,
        tool_name=tool_name or "browser_computer",
        tool_arguments=args.get("tool_arguments"),
        artifact_root=(
            Path(str(context["conversation_workspace_dir"])) / "tools" / "computer"
            if isinstance(context, dict) and context.get("conversation_workspace_dir")
            else None
        ),
        yolo_mode=False,
    )
    if not isinstance(result, dict):
        result = {"action": action, "result": result}
    is_error = bool(result.get("is_error")) or result.get("success") is False
    summary = f"{tool_name or 'browser_computer'} {result.get('action', action)}"
    summary += " failed" if is_error else " completed"
    if result.get("reason"):
        summary += f": {result['reason']}"
    if result.get("path"):
        summary += f"; artifact: {result['path']}"
    return tool_result(summary, widget={"type": tool_name or "browser_computer", **result}, is_error=is_error)


def _run_computer_action():
    """Return the host-contract runner used by the legacy function surface.

    Keeping this narrow seam preserves compatibility for callers that inject a
    test or pack-local runner.  The default runner still projects only through
    ``run_host_contract_action``; it never restores the retired local fallback.
    """

    def run_action(action, payload, context=None, **kwargs):
        del context
        source_function_id = str(kwargs.get("tool_name") or "browser_computer")
        return run_host_contract_action(
            action,
            payload,
            source_function_id=source_function_id,
        )

    return run_action


def _payload_with_context_defaults(action, payload, context):
    payload = dict(payload or {})
    if not isinstance(context, dict):
        return payload
    if action == "browser.open_url":
        target_app = context.get("computer_use_target_app")
        if isinstance(target_app, str) and target_app.strip() and not any(
            payload.get(key) for key in ("app", "application", "browser", "browser_app")
        ):
            payload["app"] = target_app.strip()
        return payload
    if action.startswith("computer.") and action not in {"computer.windows", "computer.apps"}:
        target_app = context.get("computer_use_target_app")
        target_title = context.get("computer_use_target_title")
        if isinstance(target_app, str) and target_app.strip():
            payload.setdefault("app", target_app.strip())
        if isinstance(target_title, str) and target_title.strip():
            payload.setdefault("title", target_title.strip())
        if context.get("computer_use_physical_clicks") and action in {
            "computer.click",
            "computer.drag",
            "computer.type",
            "computer.key",
            "computer.backspace",
            "computer.scroll",
        }:
            payload.setdefault("physical", True)
    return payload


_URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)


def _normalize_browser_open_url_payload(action, payload, tool_arguments=None):
    """Promote legacy value/text URL fields without granting extra authority."""

    payload = dict(payload or {})
    if action != "browser.open_url" or payload.get("url"):
        return payload
    candidates = [
        payload.get("value"),
        payload.get("text"),
        payload.get("target"),
        payload.get("href"),
    ]
    if isinstance(tool_arguments, dict):
        candidates.extend(
            [tool_arguments.get("value"), tool_arguments.get("text"), tool_arguments.get("target")]
        )
    for value in candidates:
        match = _URL_PATTERN.search(str(value or ""))
        if match:
            payload["url"] = match.group(0).rstrip(".,);]")
            break
    return payload
