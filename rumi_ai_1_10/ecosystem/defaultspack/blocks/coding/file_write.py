"""defaults.coding.file_write — ファイル書き込みブロック"""

from blocks._common import ok, error
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.coding.file_ops import FileOps
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    """ファイルに内容を書き込む。

    input_data:
        path (str): 書き込むファイルのパス
        content (str): 書き込む内容

    returns:
        {"status":"ok","data":{"path":str,"size":int,"written":true}}
    """
    path = input_data.get("path")
    if not path:
        return error("'path' is required", code="INVALID_INPUT")

    content = input_data.get("content")
    if content is None:
        return error("'content' is required", code="INVALID_INPUT")
    operation = "file.write"
    record_attempt(operation, "medium", {"path": path})
    if not is_server_approved(context, operation, input_data):
        invalid = approval_invalid_response(operation, input_data, error)
        if invalid:
            return invalid
        return ok(approval_required(operation, "medium", args=input_data, path=path))

    try:
        ops = FileOps(input_data.get("workspace_root"))
        size = ops.write_file(path, content)
        record_execution(operation, "medium", {"path": path, "size": size})
        return ok({
            "path": path,
            "size": size,
            "written": True,
        })
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        record_failure(operation, "medium", str(e), {"path": path})
        return error(str(e), code="WRITE_ERROR")
