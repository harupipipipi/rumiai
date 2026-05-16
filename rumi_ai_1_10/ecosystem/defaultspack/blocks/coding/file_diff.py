"""defaults.coding.file_diff — write前のdiff preview."""

from blocks._common import error, ok
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    path = input_data.get("path")
    if not path:
        return error("'path' is required", code="INVALID_INPUT")
    if "content" not in input_data:
        return error("'content' is required", code="INVALID_INPUT")
    try:
        workspace = resolve_workspace(input_data, context, allow_cwd_fallback=True)
        diff = FileOps(workspace.root_path).diff_text(path, input_data.get("content", ""))
        return ok(with_workspace({"path": path, "diff": diff, "has_changes": bool(diff)}, workspace))
    except ValueError as exc:
        return error(str(exc), code="PATH_TRAVERSAL")
    except Exception as exc:
        workspace_error = workspace_error_response(exc, error)
        if workspace_error:
            return workspace_error
        return error(str(exc), code="DIFF_ERROR")
