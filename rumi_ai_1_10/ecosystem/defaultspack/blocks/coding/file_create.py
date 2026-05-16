"""defaults.coding.file_create — ファイル新規作成ブロック"""

from blocks._common import ok, error
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.coding.file_ops import FileOps
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    """ファイルを新規作成する。

    input_data:
        path (str): 作成するファイルのパス
        content (str, optional): 初期内容（デフォルト: ""）

    returns:
        {"status":"ok","data":{"path":str,"created":true}}
    """
    path = input_data.get("path")
    if not path:
        return error("'path' is required", code="INVALID_INPUT")

    content = input_data.get("content", "")
    operation = "file.create"
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
        ops.create_file(path, content)
        record_execution(operation, "medium", {"path": path})
        data = {
            "path": path,
            "created": True,
        }
        if checkpoint is not None:
            data["checkpoint"] = checkpoint
        return ok(data)
    except FileExistsError as e:
        return error(str(e), code="FILE_EXISTS")
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        record_failure(operation, "medium", str(e), {"path": path})
        return error(str(e), code="CREATE_ERROR")
