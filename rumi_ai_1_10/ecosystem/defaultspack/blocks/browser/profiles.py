from __future__ import annotations

from blocks._common import error, ok

from ._runtime import profile_manager


def run(input_data, context=None):
    input_data = input_data if isinstance(input_data, dict) else {}
    method = str(input_data.get("_method") or "GET").upper()
    action = str(input_data.get("action") or ("create" if method == "POST" else "list"))
    manager = profile_manager(input_data, context)
    try:
        if action == "list":
            return ok({"profiles": manager.list_profiles(), "active_profile_id": manager.get_active_profile_id()})
        if action == "get":
            return ok({"profile": manager.get_profile(str(input_data.get("profile_id") or ""))})
        if action == "create":
            return ok(
                {
                    "profile": manager.create_profile(
                        profile_id=input_data.get("profile_id"),
                        name=input_data.get("name"),
                        browser=str(input_data.get("browser") or "chromium"),
                        schema=str(input_data.get("schema") or "managed_chromium"),
                        settings=input_data.get("settings") if isinstance(input_data.get("settings"), dict) else None,
                        metadata=input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else None,
                        set_active=input_data.get("set_active", True) is not False,
                    )
                }
            )
        if action == "update":
            return ok({"profile": manager.update_profile(str(input_data.get("profile_id") or ""), dict(input_data.get("updates") or {}))})
        if action == "delete":
            return ok(
                manager.delete_profile(
                    str(input_data.get("profile_id") or ""),
                    delete_files=bool(input_data.get("delete_files")),
                )
            )
        if action == "set_active":
            return ok(manager.set_active_profile(str(input_data.get("profile_id") or "")))
    except KeyError as exc:
        return error(str(exc), code="NOT_FOUND")
    except Exception as exc:
        return error(str(exc), code="BROWSER_PROFILE_ERROR")
    return error("unsupported browser profile action: {}".format(action), code="INVALID_ACTION")
