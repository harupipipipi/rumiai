import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.ai_client.model_search import search_models


def run(input_data, context):
    del context
    return ok(search_models(input_data if isinstance(input_data, dict) else {}))
