from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from functions._tool_common import tool_result


def _output_budget(args):
    candidates = []
    for key, ratio in (
        ("max_chars", 1),
        ("max_output_chars", 1),
        ("max_tokens", 4),
        ("max_output_tokens", 4),
    ):
        value = args.get(key)
        if value is None or value == "":
            continue
        try:
            parsed = int(value)
        except Exception:
            return None
        if parsed > 0:
            candidates.append(parsed * ratio)
    if not candidates:
        return None
    return max(200, min(min(candidates), 120_000))


def _clip_content(content, budget):
    text = str(content or "")
    if budget is None or len(text) <= budget:
        return text, False
    return text[: max(0, budget - 28)].rstrip() + "\n[truncated]", True


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

        content = FileOps(workspace_root).read_file(path)
        clipped, truncated = _clip_content(content, _output_budget(args))
        widget = {
            "type": "file_reader",
            "path": path,
            "size": len(str(content).encode("utf-8")),
            "returned_size": len(str(clipped).encode("utf-8")),
            "truncated": truncated,
        }
        return tool_result(clipped, widget=widget)
    except Exception as exc:
        return tool_result(str(exc), is_error=True)
