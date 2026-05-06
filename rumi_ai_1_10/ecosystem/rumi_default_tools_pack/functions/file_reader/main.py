from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def run(context, args):
    path = args.get("path", "")
    return tool_result("File content from: {} (stub)".format(path))
