import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.ai_client.model_router import route_model_request


def run(input_data, context):
    del context
    return ok(route_model_request(input_data if isinstance(input_data, dict) else {}).to_dict())
