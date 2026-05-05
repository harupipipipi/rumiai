from __future__ import annotations

from blocks._common import error, ok

from ._runtime import profile_manager


def run(input_data, context=None):
    try:
        return ok(profile_manager(input_data, context).set_active_profile(str(input_data.get("profile_id") or input_data.get("id") or "")))
    except Exception as exc:
        return error(str(exc), code="BROWSER_PROFILE_ERROR")
