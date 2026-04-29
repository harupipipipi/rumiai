import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok
from domain.tool.browser_computer import BrowserComputerController


def run(input_data, context=None):
    action = input_data.get("action")
    if not action:
        return error("'action' is required", code="INVALID_INPUT")
    try:
        result = BrowserComputerController().run(str(action), dict(input_data.get("payload") or {}))
    except Exception as exc:
        return error(str(exc), code="BROWSER_COMPUTER_FAILED")
    return ok(result)
