"""Read-only legacy projection over the model profile owner."""

from blocks._common import error, ok
from ecosystem.defaultspack.backend.ai_client.provider_catalog import (
    list_profile_catalog,
)


def run(input_data, context):
    del context
    method = str(input_data.get("_method") or "GET").upper()
    if method == "GET":
        profiles = list_profile_catalog()
        return ok({"profiles": profiles, "count": len(profiles)})
    return error(
        "legacy profile writer was removed; use rumi.action.ai.model.profile.manage.v1",
        "MIGRATED_OWNER_REQUIRED",
    )
