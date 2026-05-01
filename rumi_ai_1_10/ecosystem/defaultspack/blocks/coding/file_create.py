"""defaults.coding.file_create — ファイル新規作成ブロック"""

from blocks._common import ok, error
from blocks.coding._approval import has_server_approval
from domain.coding.file_ops import FileOps


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
    if not has_server_approval(context):
        return ok({
            "approval_required": True,
            "risk_level": "medium",
            "operation": "file.create",
            "path": path,
        })

    try:
        ops = FileOps()
        ops.create_file(path, content)
        return ok({
            "path": path,
            "created": True,
        })
    except FileExistsError as e:
        return error(str(e), code="FILE_EXISTS")
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        return error(str(e), code="CREATE_ERROR")
