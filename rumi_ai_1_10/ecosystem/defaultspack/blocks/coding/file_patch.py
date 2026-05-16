"""defaults.coding.file_patch — old/new replacement patch."""

from blocks._common import error, ok
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.coding.file_ops import FileOps
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    path = input_data.get("path")
    old = input_data.get("old")
    new = input_data.get("new")
    if not path:
        return error("'path' is required", code="INVALID_INPUT")
    if old is None or new is None:
        return error("'old' and 'new' are required", code="INVALID_INPUT")
    operation = "file.patch"
    record_attempt(operation, "medium", {"path": path})
    if not is_server_approved(context, operation, input_data):
        invalid = approval_invalid_response(operation, input_data, error)
        if invalid:
            return invalid
        return ok(approval_required(operation, "medium", args=input_data, path=path))
    try:
        ops = FileOps(input_data.get("workspace_root"))
        checkpoint = None
        if input_data.get("checkpoint", True) is not False:
            checkpoint = ops.checkpoint_before_mutation(
                operation,
                [path],
                metadata={"path": path},
            )
        result = ops.apply_patch_text(path, old, new)
        if checkpoint is not None:
            result["checkpoint"] = checkpoint
        record_execution(operation, "medium", {"path": path})
        return ok(result)
    except ValueError as exc:
        record_failure(operation, "medium", str(exc), {"path": path})
        return error(str(exc), code="PATCH_ERROR")
    except Exception as exc:
        return error(str(exc), code="PATCH_ERROR")
