"""defaults.coding.file_delete — ファイル削除ブロック"""

from blocks._common import ok, error
from blocks.coding._approval import has_server_approval
from domain.coding.file_ops import FileOps


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
    if not has_server_approval(context):
        return ok({
            "approval_required": True,
            "risk_level": "high",
            "operation": "file.delete",
            "path": path,
        })

    try:
        ops = FileOps()
        ops.delete_file(path)
        return ok({
            "path": path,
            "deleted": True,
        })
    except FileNotFoundError as e:
        return error(str(e), code="FILE_NOT_FOUND")
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        return error(str(e), code="DELETE_ERROR")
