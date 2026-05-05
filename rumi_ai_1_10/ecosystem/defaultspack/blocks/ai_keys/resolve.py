import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.ai_client.key_resolver import KeyResolver


def run(input_data, context):
    del context
    resolver = KeyResolver()
    resolved = resolver.resolve_api_key(
        provider_id=(input_data or {}).get("provider_id", ""),
        profile_id=(input_data or {}).get("profile_id", ""),
        agent_id=(input_data or {}).get("agent_id", ""),
        preferred_key_id=(input_data or {}).get("preferred_key_id", ""),
        model=(input_data or {}).get("model", ""),
        fallback=(input_data or {}).get("fallback", ""),
        record_usage=bool((input_data or {}).get("record_usage", False)),
    )
    return ok({"resolution": resolver.redacted_resolution(resolved)})
