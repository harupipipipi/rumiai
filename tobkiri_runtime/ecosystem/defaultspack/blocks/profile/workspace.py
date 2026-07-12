import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from core_runtime.profile_workspace import ProfileWorkspaceManager


def run(input_data, context):
    del context
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = str(data.get("profile_id") or "").strip()
    if not profile_id:
        return error("profile_id is required", "MISSING_PROFILE")
    manager = ProfileWorkspaceManager()
    profile = manager.load_profile_yaml(profile_id) or {"profile_id": profile_id}
    paths = manager.initialize_profile_workspace(profile)
    return ok(manager.payload_for_profile(paths.profile_id))
