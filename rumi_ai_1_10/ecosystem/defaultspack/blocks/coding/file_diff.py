"""defaults.coding.file_diff — write前のdiff preview."""

from blocks._common import error, ok
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    path = input_data.get("path")
    if not path:
        return error("'path' is required", code="INVALID_INPUT")
    if "content" not in input_data:
        return error("'content' is required", code="INVALID_INPUT")
    try:
        diff = FileOps(input_data.get("workspace_root")).diff_text(path, input_data.get("content", ""))
        return ok({"path": path, "diff": diff, "has_changes": bool(diff)})
    except ValueError as exc:
        return error(str(exc), code="PATH_TRAVERSAL")
    except Exception as exc:
        return error(str(exc), code="DIFF_ERROR")
