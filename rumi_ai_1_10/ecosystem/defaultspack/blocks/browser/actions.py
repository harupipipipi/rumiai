from __future__ import annotations

from blocks._common import error, ok

from ._runtime import session_manager


def run(input_data, context=None):
    try:
        profile_id = str(input_data.get("profile_id") or input_data.get("id") or "default")
        action = str(input_data.get("action") or "")
        payload = dict(input_data.get("payload") or {})
        session_id = str(payload.get("session_id") or input_data.get("session_id") or f"session-{profile_id}")
        manager = session_manager(input_data, context)
        if action in {"start", "browser.session.start"}:
            return ok(manager.start_session(session_id=session_id, profile_id=profile_id, url=payload.get("url")))
        if action in {"stop", "browser.session.stop"}:
            return ok(manager.stop_session(session_id))
        if action in {"restart", "browser.session.restart"}:
            return ok(manager.restart_session(session_id))
        if action in {"health", "browser.session.health"}:
            return ok(manager.health(session_id))
        if action in {"tabs", "list_tabs", "browser.tab.list"}:
            return ok(manager.list_tabs(session_id))
        if action in {"open_tab", "open", "navigate", "browser.tab.open"}:
            return ok(manager.open_tab(session_id=session_id, url=str(payload.get("url") or "about:blank")))
        if action in {"snapshot", "browser.tab.snapshot"}:
            return ok(manager.snapshot_tab(session_id=session_id, tab_id=payload.get("tab_id")))
        if action in {"screenshot", "browser.tab.screenshot"}:
            return ok(manager.screenshot_tab(session_id=session_id, tab_id=payload.get("tab_id")))
        raise ValueError("unsupported browser profile action")
    except Exception as exc:
        return error(str(exc), code="BROWSER_ACTION_ERROR")
