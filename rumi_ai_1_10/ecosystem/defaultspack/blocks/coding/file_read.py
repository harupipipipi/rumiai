"""defaults.coding.file_read — ファイル読み取りブロック"""

from blocks._common import ok, error
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    """ファイルを読み取って内容を返す。

    input_data:
        path (str): 読み取るファイルのパス

    returns:
        {"status":"ok","data":{"path":str,"content":str,"size":int,"encoding":"utf-8"}}
    """
    path = input_data.get("path")
    if not path:
        return error("'path' is required", code="INVALID_INPUT")

    try:
        workspace = resolve_workspace(input_data, context, allow_cwd_fallback=True)
        ops = FileOps(workspace.root_path)
        content = ops.read_file(path)
        return ok(with_workspace({
            "path": path,
            "content": content,
            "size": len(content.encode("utf-8")),
            "encoding": "utf-8",
        }, workspace))
    except FileNotFoundError as e:
        return error(str(e), code="FILE_NOT_FOUND")
    except PermissionError as e:
        return error(str(e), code="PATH_RESTRICTED")
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        return error(str(e), code="READ_ERROR")
