from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from domain.tool.introspection import current_tool_names


def run(input_data, context):
    return ok(current_tool_names(input_data if isinstance(input_data, dict) else {}, context))
