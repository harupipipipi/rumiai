from __future__ import annotations

from blocks._common import error, ok

from ._runtime import session_manager


def run(input_data, context=None):
    try:
        profile_id = str(input_data.get("profile_id") or input_data.get("id") or "default")
        return ok(session_manager(input_data, context).snapshot_tab(
            session_id=str(input_data.get("session_id") or f"session-{profile_id}"),
            tab_id=input_data.get("tab_id") or input_data.get("target_id"),
        ))
    except Exception as exc:
        return error(str(exc), code="BROWSER_SNAPSHOT_ERROR")
