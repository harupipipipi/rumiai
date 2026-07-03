import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import ok, error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.frontend.registry import FrontendRegistry


def _bool_with_default(value, default=False):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def run(input_data, context):
    registry = FrontendRegistry()
    method = (input_data or {}).get("_method", "GET").upper()
    if method == "GET":
        return ok(registry.get_settings(lightweight=not _bool_with_default((input_data or {}).get("full"), False)))
    if method == "PUT":
        values = (input_data or {}).get("values")
        if not isinstance(values, dict):
            return error("values dict is required", "INVALID_INPUT")
        return ok({"values": registry.update_settings(values)})
    return error("unsupported method", "METHOD_NOT_ALLOWED")
