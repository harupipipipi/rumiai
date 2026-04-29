import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import error, ok

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.capability.catalog import CapabilityCatalog


def run(input_data, context):
    del context
    capability_id = input_data.get("id") or input_data.get("capability_id")
    if not capability_id:
        return error("capability_id is required", "MISSING_PARAM")
    capability = CapabilityCatalog().get(capability_id)
    if capability is None:
        return error(f"capability not found: {capability_id}", "NOT_FOUND")
    return ok({"capability": capability})
