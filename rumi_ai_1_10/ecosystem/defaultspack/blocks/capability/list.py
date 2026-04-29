import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import ok

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.capability.catalog import CapabilityCatalog


def run(input_data, context):
    del context
    catalog = CapabilityCatalog()
    capabilities = catalog.list_capabilities(
        local_only=input_data.get("local_only"),
        risk_level=input_data.get("risk_level"),
        requires_network=input_data.get("requires_network"),
    )
    return ok({"capabilities": capabilities, "summary": catalog.summary(), "count": len(capabilities)})
