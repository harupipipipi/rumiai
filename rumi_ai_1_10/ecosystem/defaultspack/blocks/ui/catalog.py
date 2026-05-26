import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import ok
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.frontend.registry import FrontendRegistry


def run(input_data, context):
    data = input_data if isinstance(input_data, dict) else {}
    registry = FrontendRegistry()
    return ok(registry.build_catalog(profile_id=str(data.get("profile_id") or "").strip() or None))
