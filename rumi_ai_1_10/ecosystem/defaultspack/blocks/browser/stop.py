from __future__ import annotations

from blocks._common import error, ok

from ._runtime import session_manager


def run(input_data, context=None):
    try:
        profile_id = str(input_data.get("profile_id") or input_data.get("id") or "default")
        return ok(session_manager(input_data, context).stop_session(str(input_data.get("session_id") or f"session-{profile_id}")))
    except Exception as exc:
        return error(str(exc), code="BROWSER_SESSION_ERROR")
