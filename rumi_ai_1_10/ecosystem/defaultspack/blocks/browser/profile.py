from __future__ import annotations

from blocks._common import error, ok

from ._runtime import profile_manager


def run(input_data, context=None):
    try:
        manager = profile_manager(input_data, context)
        profile_id = str(input_data.get("profile_id") or input_data.get("id") or "")
        method = str(input_data.get("_method") or "GET").upper()
        if method == "PUT":
            updates = dict(input_data.get("updates") or {key: value for key, value in input_data.items() if not str(key).startswith("_")})
            return ok({"profile": manager.update_profile(profile_id, updates)})
        if method == "DELETE":
            return ok(manager.delete_profile(profile_id, delete_files=bool(input_data.get("delete_files"))))
        return ok({"profile": manager.get_profile(profile_id)})
    except KeyError as exc:
        return error(str(exc), code="NOT_FOUND")
    except Exception as exc:
        return error(str(exc), code="BROWSER_PROFILE_ERROR")
