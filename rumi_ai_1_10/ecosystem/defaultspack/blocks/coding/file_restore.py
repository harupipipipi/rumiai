"""defaults.coding.file_restore — restore workspace snapshot."""

from blocks._common import error, ok
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.coding.file_ops import FileOps
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    snapshot_id = input_data.get("snapshot_id")
    if not snapshot_id:
        return error("'snapshot_id' is required", code="INVALID_INPUT")
    operation = "file.restore"
    record_attempt(operation, "high", {"snapshot_id": snapshot_id})
    if not is_server_approved(context, operation, input_data):
        invalid = approval_invalid_response(operation, input_data, error)
        if invalid:
            return invalid
        return ok(approval_required(operation, "high", args=input_data, snapshot_id=snapshot_id))
    try:
        paths = input_data.get("paths")
        if paths is not None and not isinstance(paths, list):
            return error("'paths' must be a list", code="INVALID_INPUT")
        result = FileOps(input_data.get("workspace_root")).restore_snapshot(snapshot_id, paths=paths)
        record_execution(operation, "high", {"snapshot_id": snapshot_id, "paths": paths})
        return ok(result)
    except Exception as exc:
        record_failure(operation, "high", str(exc), {"snapshot_id": snapshot_id})
        return error(str(exc), code="RESTORE_ERROR")
