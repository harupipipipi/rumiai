from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _host_mediator import run_host_mediator


def run(context, args):
    return run_host_mediator(context, args, function_id="host_input_keyboard", operation="host.input.keyboard", stream_allowed=False)
