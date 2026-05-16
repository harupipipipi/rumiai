"""defaults.coding.file_delete — ファイル削除ブロック"""

from blocks._common import ok, error
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.coding.file_ops import FileOps
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    """ファイルを削除する。

    input_data:
        path (str): 削除するファイルのパス

    returns:
        {"status":"ok","data":{"path":str,"deleted":true}}
    """
    path = input_data.get("path")
    if not path:
        return error("'path' is required", code="INVALID_INPUT")
    operation = "file.delete"
    record_attempt(operation, "high", {"path": path})
    if not is_server_approved(context, operation, input_data):
        invalid = approval_invalid_response(operation, input_data, error)
        if invalid:
            return invalid
        return ok(approval_required(operation, "high", args=input_data, path=path))

    try:
        ops = FileOps(input_data.get("workspace_root"))
        checkpoint = None
        if input_data.get("checkpoint", True) is not False:
            checkpoint = ops.checkpoint_before_mutation(
                operation,
                [path],
                metadata={"path": path},
            )
        ops.delete_file(path)
        record_execution(operation, "high", {"path": path})
        data = {
            "path": path,
            "deleted": True,
        }
        if checkpoint is not None:
            data["checkpoint"] = checkpoint
        return ok(data)
    except FileNotFoundError as e:
        return error(str(e), code="FILE_NOT_FOUND")
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        record_failure(operation, "high", str(e), {"path": path})
        return error(str(e), code="DELETE_ERROR")
