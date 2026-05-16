from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def run(context, args):
    if not isinstance(args, dict):
        return tool_result("args must be a dict", is_error=True)

    path = args.get("path", "")
    if not path:
        return tool_result("path is required", is_error=True)

    workspace_root = args.get("workspace_root")
    if not workspace_root and isinstance(context, dict):
        workspace_root = context.get("workspace_root")

    try:
        from ecosystem.defaultspack.domain.coding.file_ops import FileOps

        return tool_result(FileOps(workspace_root).read_file(path))
    except Exception as exc:
        return tool_result(str(exc), is_error=True)
