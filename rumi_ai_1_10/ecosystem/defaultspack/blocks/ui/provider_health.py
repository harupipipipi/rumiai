import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import ok

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.ai_client.provider_health import provider_health_report


def _provider_ids(input_data):
    raw = (input_data or {}).get("provider_ids") or (input_data or {}).get("provider_id")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [item.strip() for item in raw.replace(",", "\n").splitlines() if item.strip()]
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def run(input_data, context):
    del context
    return ok(provider_health_report(provider_ids=_provider_ids(input_data)))
