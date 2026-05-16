"""defaults.coding.context — coding workspace context."""

from blocks._common import ok, error
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.file_ops import FileOps
from domain.coding.git_ops import GitOps


def run(input_data, context=None):
    """Return a compact workspace context for coding UI wiring."""
    directory = input_data.get("directory", ".")
    try:
        workspace = resolve_workspace(input_data, context, allow_cwd_fallback=True)
        ops = FileOps(workspace.root_path)
        entries = ops.list_files(directory, recursive=False)
        git = GitOps(workspace.root_path)
        try:
            git_status = git.status()
        except Exception:
            git_status = None
        return ok(with_workspace({
            "branch": git_status.get("branch") if git_status else None,
            "root_folder": ops.root,
            "directory": directory,
            "files": [item["path"] for item in entries if not item.get("is_dir")],
            "entries": entries,
            "git": git_status,
        }, workspace))
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        return error(str(e), code="CONTEXT_ERROR")
