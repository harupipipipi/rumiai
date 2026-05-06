from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def run(context, args):
    from ecosystem.rumi_default_tools_pack.domain.tool.rumi_api import run as run_rumi_api

    return run_rumi_api(args, context if isinstance(context, dict) else {})
