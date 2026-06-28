from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def run(context, args):
    from ecosystem.rumi_default_tools_pack.domain.tool.subagent import SubagentController

    result = SubagentController().run(args, context if isinstance(context, dict) else {})
    return tool_result(
        result.get("summary", "subagent completed"),
        is_error=bool(result.get("is_error")),
        widget={"type": "subagent", **result},
    )
