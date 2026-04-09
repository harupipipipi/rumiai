import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.ai_client.client import AIClient


def run(input_data, context):
    provider = input_data.get("provider")

    client = AIClient()
    models = client.list_models(provider=provider)
    return ok({"models": models})
