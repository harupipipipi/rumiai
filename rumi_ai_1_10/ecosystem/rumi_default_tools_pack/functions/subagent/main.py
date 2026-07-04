from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def run(context, args):
    from ecosystem.rumi_default_tools_pack.domain.tool.subagent import SubagentController
    from domain.agent.subagent_delegation import SubagentDelegationError

    try:
        result = SubagentController().run(args, context if isinstance(context, dict) else {})
    except SubagentDelegationError as exc:
        payload = exc.to_result()
        return tool_result(
            payload["delegation_error"]["message"],
            widget={"type": "subagent", **payload},
            is_error=True,
        )
    return tool_result(result.get("summary", "subagent completed"), widget={"type": "subagent", **result})
