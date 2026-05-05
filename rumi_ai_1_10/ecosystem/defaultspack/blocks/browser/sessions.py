from __future__ import annotations

from blocks._common import error, ok

from ._runtime import session_manager


def run(input_data, context=None):
    input_data = input_data if isinstance(input_data, dict) else {}
    action = str(input_data.get("action") or "health")
    manager = session_manager(input_data, context)
    try:
        if action == "list":
            return ok({"sessions": manager.list_sessions()})
        if action == "start":
            return ok(
                manager.start_session(
                    session_id=input_data.get("session_id"),
                    profile_id=input_data.get("profile_id"),
                    url=input_data.get("url"),
                    debugging_port=input_data.get("debugging_port"),
                    launch=input_data.get("launch", True) is not False,
                    extra_args=input_data.get("extra_args") if isinstance(input_data.get("extra_args"), list) else None,
                )
            )
        if action == "stop":
            return ok(manager.stop_session(input_data.get("session_id")))
        if action == "restart":
            return ok(manager.restart_session(input_data.get("session_id")))
        if action == "health":
            return ok(manager.health(input_data.get("session_id")))
    except KeyError as exc:
        return error(str(exc), code="NOT_FOUND")
    except Exception as exc:
        return error(str(exc), code="BROWSER_SESSION_ERROR")
    return error("unsupported browser session action: {}".format(action), code="INVALID_ACTION")
