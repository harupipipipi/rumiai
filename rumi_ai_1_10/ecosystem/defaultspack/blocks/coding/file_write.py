"""defaults.coding.file_write — ファイル書き込みブロック"""

from blocks._common import ok, error
from blocks.coding._approval import has_server_approval
from domain.coding.file_ops import FileOps


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
    if not has_server_approval(context):
        return ok({
            "approval_required": True,
            "risk_level": "medium",
            "operation": "file.write",
            "path": path,
        })

    try:
        ops = FileOps()
        size = ops.write_file(path, content)
        return ok({
            "path": path,
            "size": size,
            "written": True,
        })
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        return error(str(e), code="WRITE_ERROR")
