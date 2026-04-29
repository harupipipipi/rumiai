"""defaults.coding.file_restore — restore workspace snapshot."""

from blocks._common import error, ok
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    snapshot_id = input_data.get("snapshot_id")
    if not snapshot_id:
        return error("'snapshot_id' is required", code="INVALID_INPUT")
    if not input_data.get("approved", False):
        return ok(
            {
                "approval_required": True,
                "risk_level": "high",
                "operation": "file.restore",
                "snapshot_id": snapshot_id,
            }
        )
    try:
        paths = input_data.get("paths")
        if paths is not None and not isinstance(paths, list):
            return error("'paths' must be a list", code="INVALID_INPUT")
        return ok(FileOps(input_data.get("workspace_root")).restore_snapshot(snapshot_id, paths=paths))
    except Exception as exc:
        return error(str(exc), code="RESTORE_ERROR")
