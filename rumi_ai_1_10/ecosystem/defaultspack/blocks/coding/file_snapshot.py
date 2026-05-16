"""defaults.coding.file_snapshot — workspace snapshot."""

from blocks._common import error, ok
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    try:
        paths = input_data.get("paths")
        if isinstance(paths, str):
            paths = [paths]
        if paths is not None and not (
            isinstance(paths, list) and all(isinstance(path, str) for path in paths)
        ):
            return error("'paths' must be a string or list of strings", code="INVALID_INPUT")
        metadata = input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {}
        workspace = resolve_workspace(input_data, context, mutation=True, operation="file.snapshot")
        return ok(
            with_workspace(FileOps(workspace.root_path).snapshot(
                paths=paths,
                metadata=metadata,
                include_missing=bool(input_data.get("include_missing", False)),
            ), workspace)
        )
    except Exception as exc:
        workspace_error = workspace_error_response(exc, error)
        if workspace_error:
            return workspace_error
        return error(str(exc), code="SNAPSHOT_ERROR")
