import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok, error
from domain.ai_client.model_search import get_model_capabilities


def run(input_data, context):
    del context
    profile_id = str((input_data or {}).get("profile_id") or (input_data or {}).get("model") or "").strip()
    if not profile_id:
        return error("profile_id is required", "MISSING_PARAM")
    capabilities = get_model_capabilities(profile_id)
    if capabilities is None:
        return error("model not found", "NOT_FOUND")
    return ok(capabilities)
