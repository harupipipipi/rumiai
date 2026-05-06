from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def run(context, args):
    from domain.research.providers import ExternalWebProvider

    result = ExternalWebProvider().search(
        args.get("query", ""),
        limit=int(args.get("limit", 5)),
        allow_network=bool(args.get("allow_network", True)),
    )
    return tool_result(result.summary, widget={"type": "research_sources", **result.as_dict()})
