from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import ok

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.coding.frontend_precision import frontend_command_payload


def run(input_data, context=None):
    payload = frontend_command_payload(input_data if isinstance(input_data, dict) else {}, context or {})
    return ok(payload)
