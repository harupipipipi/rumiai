from __future__ import annotations

from blocks._common import error, ok

from ._runtime import session_manager


def run(input_data, context=None):
    input_data = input_data if isinstance(input_data, dict) else {}
    action = str(input_data.get("action") or "list")
    manager = session_manager(input_data, context)
    session_id = input_data.get("session_id")
    tab_id = input_data.get("tab_id")
    try:
        if action == "list":
            return ok(manager.list_tabs(session_id))
        if action == "open":
            return ok(manager.open_tab(url=str(input_data.get("url") or "about:blank"), session_id=session_id))
        if action == "focus":
            return ok(manager.focus_tab(tab_id=str(tab_id or ""), session_id=session_id))
        if action == "close":
            return ok(manager.close_tab(tab_id=str(tab_id or ""), session_id=session_id))
        if action == "navigate":
            return ok(manager.navigate_tab(url=str(input_data.get("url") or ""), tab_id=tab_id, session_id=session_id))
        if action == "snapshot":
            return ok(manager.snapshot_tab(tab_id=tab_id, session_id=session_id))
        if action == "screenshot":
            return ok(
                manager.screenshot_tab(
                    tab_id=tab_id,
                    session_id=session_id,
                    format=str(input_data.get("format") or "png"),
                    quality=input_data.get("quality"),
                )
            )
        if action in {"click_ref", "type_ref", "key_ref", "scroll_ref"}:
            payload = dict(input_data.get("payload") or {})
            for key in ("text", "key", "amount"):
                if key in input_data:
                    payload[key] = input_data[key]
            return ok(
                manager.execute_ref_action(
                    action=action.removesuffix("_ref"),
                    ref_id=input_data.get("ref_id") or input_data.get("ref"),
                    session_id=session_id,
                    tab_id=tab_id,
                    payload=payload,
                    current_snapshot=input_data.get("current_snapshot") if isinstance(input_data.get("current_snapshot"), dict) else None,
                )
            )
    except KeyError as exc:
        return error(str(exc), code="NOT_FOUND")
    except Exception as exc:
        return error(str(exc), code="BROWSER_TAB_ERROR")
    return error("unsupported browser tab action: {}".format(action), code="INVALID_ACTION")
