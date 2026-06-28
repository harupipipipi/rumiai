from __future__ import annotations

import sys
from pathlib import Path

_FUNCTION_PATH = Path(__file__).resolve()
for _path in (_FUNCTION_PATH.parents[4], _FUNCTION_PATH.parents[2]):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)


def run(context, args):
    from ecosystem.rumi_default_tools_pack.domain.tool.rumi_api import run as run_rumi_api

    return run_rumi_api(args, context if isinstance(context, dict) else {})
