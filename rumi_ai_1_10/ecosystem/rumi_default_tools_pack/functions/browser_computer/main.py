from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def run(context, args):
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    action = str(args.get("action", "browser.session"))
    payload = dict(args.get("payload") or {})
    artifact_root = None
    workspace = context.get("conversation_workspace_dir") if isinstance(context, dict) else None
    if isinstance(workspace, str) and workspace:
        artifact_root = Path(workspace) / "tools" / "computer"
    result = BrowserComputerController(artifact_root=artifact_root).run(
        action,
        payload,
        yolo_mode=bool(context.get("yolo_mode")) if isinstance(context, dict) else False,
    )
    summary = "browser_computer {} completed".format(result.get("action", "action"))
    if result.get("path"):
        summary += "; artifact: {}".format(result.get("path"))
    return tool_result(summary, widget={"type": "browser_computer", **result})
