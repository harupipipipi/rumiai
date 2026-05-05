from __future__ import annotations

from blocks._common import error, ok

from ._runtime import session_manager


def run(input_data, context=None):
    try:
        profile_id = str(input_data.get("profile_id") or input_data.get("id") or "default")
        return ok(session_manager(input_data, context).start_session(
            session_id=str(input_data.get("session_id") or f"session-{profile_id}"),
            profile_id=profile_id,
            url=str(input_data.get("url") or "about:blank"),
            debugging_port=input_data.get("debugging_port"),
            launch=input_data.get("launch", True) is not False,
        ))
    except Exception as exc:
        return error(str(exc), code="BROWSER_SESSION_ERROR")
