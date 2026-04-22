import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from backend.ai_client.provider_catalog import list_provider_catalog
from domain.ai_client.client import AIClient


def run(input_data, context):
    del input_data, context
    client = AIClient()
    registered = {
        str(provider.get("provider_id") or provider.get("id", "")): provider
        for provider in client.list_providers()
        if isinstance(provider, dict) and (provider.get("provider_id") or provider.get("id"))
    }
    providers = []
    for provider in list_provider_catalog():
        merged = dict(provider)
        merged["registered"] = provider["provider_id"] in registered
        if merged["registered"]:
            merged["runtime"] = registered[provider["provider_id"]]
            merged["status"] = "registered"
        providers.append(merged)
    return ok({"providers": providers, "count": len(providers)})
