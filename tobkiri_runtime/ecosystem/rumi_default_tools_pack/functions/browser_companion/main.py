from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def run(context, args):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_companion import BrowserCompanionController

    raw = dict(args or {})
    action = str(raw.get("action") or "session")
    payload = {key: value for key, value in raw.items() if key != "action"}
    artifact_root = None
    workspace = context.get("conversation_workspace_dir") if isinstance(context, dict) else None
    if isinstance(workspace, str) and workspace:
        artifact_root = Path(workspace) / "tools" / "browser_companion"
    result = BrowserCompanionController(artifact_root=artifact_root).run(
        action,
        payload,
        context=context if isinstance(context, dict) else {},
    )
    summary = f"browser_companion {result.get('action', action)} {'failed' if result.get('is_error') else 'completed'}"
    if result.get("reason"):
        summary += f": {result.get('reason')}"
    if result.get("path"):
        summary += f"; artifact: {result.get('path')}"
    return tool_result(summary, widget={"type": "browser_companion", **result}, is_error=bool(result.get("is_error")))
