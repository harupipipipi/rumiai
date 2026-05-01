"""defaults.coding.context — coding workspace context."""

import os

from blocks._common import ok, error
from domain.coding.file_ops import FileOps
from domain.coding.git_ops import GitOps


def run(input_data, context=None):
    """Return a compact workspace context for coding UI wiring."""
    workspace_root = input_data.get("workspace_root") or os.getcwd()
    directory = input_data.get("directory", ".")
    try:
        ops = FileOps(workspace_root)
        files = ops.list_files(directory, recursive=False)
        git = GitOps(workspace_root)
        try:
            git_status = git.status()
        except Exception:
            git_status = None
        return ok({
            "workspace_root": ops.root,
            "directory": directory,
            "files": files,
            "git": git_status,
        })
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        return error(str(e), code="CONTEXT_ERROR")
