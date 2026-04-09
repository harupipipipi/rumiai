import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.ai_client.client import AIClient


def run(input_data, context):
    client = AIClient()
    providers = client.list_providers()
    return ok({"providers": providers})
