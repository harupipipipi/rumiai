"""defaults.coding.file_checkpoint - create and list workspace checkpoints."""

from blocks._common import error, ok
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.file_ops import FileOps
from domain.coding.workspace_policy import require_registered_trusted_workspace


def _coerce_paths(raw_paths):
    if raw_paths is None:
        return ["."]
    if isinstance(raw_paths, str):
        return [raw_paths]
    if isinstance(raw_paths, list) and all(isinstance(path, str) for path in raw_paths):
        return raw_paths
    raise ValueError("'paths' must be a string or list of strings")


def run(input_data, context=None):
    context = context or {}
    method = str(input_data.get("_method") or input_data.get("method") or "POST").upper()
    try:
        operation = "file.checkpoint.list" if method == "GET" else "file.checkpoint.create"
        workspace = require_registered_trusted_workspace(
            resolve_workspace(input_data, context),
            operation=operation,
        )
        ops = FileOps(workspace.root_path)
        if method == "GET":
            limit = int(input_data.get("limit", 50))
            return ok(with_workspace({"checkpoints": ops.list_snapshots(limit=limit)}, workspace))
        if method != "POST":
            return error("unsupported method: " + method, code="INVALID_INPUT")

        paths = _coerce_paths(input_data.get("paths"))
        metadata = input_data.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        checkpoint_metadata = {
            "operation": str(input_data.get("operation") or "manual"),
            "kind": "manual",
        }
        checkpoint_metadata.update(metadata)
        checkpoint = ops.worktree_checkpoint(
            paths=paths,
            metadata=checkpoint_metadata,
            include_missing=True,
        )
        return ok(with_workspace({"checkpoint": checkpoint}, workspace))
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        workspace_error = workspace_error_response(exc, error)
        if workspace_error:
            return workspace_error
        return error(str(exc), code="CHECKPOINT_ERROR")
