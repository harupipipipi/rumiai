import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.tool.ui_compiler_tools import ui_generation_status


def run(input_data, context):
    return ui_generation_status(input_data, context if isinstance(context, dict) else {})
