from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.ui_compiler.service import compile_ui_plan  # noqa: E402


def run(input_data, context):
    return compile_ui_plan(input_data if isinstance(input_data, dict) else {}, context)
