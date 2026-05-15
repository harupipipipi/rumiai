"""defaults.coding.file_restore — restore workspace snapshot."""

from blocks._common import error, ok
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.file_ops import FileOps
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    snapshot_id = input_data.get("snapshot_id")
    if not snapshot_id:
        return error("'snapshot_id' is required", code="INVALID_INPUT")
    operation = "file.restore"
    record_attempt(operation, "high", {"snapshot_id": snapshot_id})
    try:
        workspace = resolve_workspace(input_data, context, mutation=True, operation=operation)
    except Exception as exc:
        workspace_error = workspace_error_response(exc, error)
        if workspace_error:
            return workspace_error
        return error(str(exc), code="WORKSPACE_ERROR")
    if not is_server_approved(context, operation, input_data):
        invalid = approval_invalid_response(operation, input_data, error)
        if invalid:
            return invalid
        return ok(approval_required(operation, "high", args=input_data, snapshot_id=snapshot_id))
    try:
        paths = input_data.get("paths")
        if paths is not None and not isinstance(paths, list):
            return error("'paths' must be a list", code="INVALID_INPUT")
        result = FileOps(workspace.root_path).restore_snapshot(snapshot_id, paths=paths)
        record_execution(operation, "high", {"snapshot_id": snapshot_id, "paths": paths})
        return ok(with_workspace(result, workspace))
    except Exception as exc:
        workspace_error = workspace_error_response(exc, error)
        if workspace_error:
            return workspace_error
        record_failure(operation, "high", str(exc), {"snapshot_id": snapshot_id})
        return error(str(exc), code="RESTORE_ERROR")
