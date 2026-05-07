import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.gateway.server import get_gateway_server


def run(input_data, context=None):
    input_data = input_data if isinstance(input_data, dict) else {}
    return ok(get_gateway_server().start(input_data.get("host", "127.0.0.1"), int(input_data.get("port", 18789))))
