"""defaults.coding.file_read — ファイル読み取りブロック"""

from blocks._common import ok, error
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    """ファイルを読み取って内容を返す。

    input_data:
        path (str): 読み取るファイルのパス
        start_line (int, optional): 1-based inclusive start line
        end_line (int, optional): 1-based inclusive end line

    returns:
        {"status":"ok","data":{"path":str,"content":str,"size":int,"encoding":"utf-8"}}
    """
    path = input_data.get("path")
    if not path:
        return error("'path' is required", code="INVALID_INPUT")
    start_line = input_data.get("start_line")
    end_line = input_data.get("end_line")
    if start_line is not None:
        try:
            start_line = int(start_line)
        except Exception:
            return error("'start_line' must be an integer", code="INVALID_INPUT")
        if start_line < 1:
            return error("'start_line' must be >= 1", code="INVALID_INPUT")
    if end_line is not None:
        try:
            end_line = int(end_line)
        except Exception:
            return error("'end_line' must be an integer", code="INVALID_INPUT")
        if end_line < 1:
            return error("'end_line' must be >= 1", code="INVALID_INPUT")
    if start_line is not None and end_line is not None and end_line < start_line:
        return error("'end_line' must be >= 'start_line'", code="INVALID_INPUT")

    try:
        workspace = resolve_workspace(input_data, context, allow_cwd_fallback=True)
        ops = FileOps(workspace.root_path)
        if start_line is not None or end_line is not None:
            window = ops.read_file_lines(path, start_line=start_line, end_line=end_line)
            payload = {
                "path": path,
                "content": window["content"],
                "size": len(window["content"].encode("utf-8")),
                "encoding": "utf-8",
                "start_line": window["start_line"],
                "end_line": window["end_line"],
                "total_lines": window["total_lines"],
                "truncated": window["truncated"],
            }
        else:
            content = ops.read_file(path)
            payload = {
                "path": path,
                "content": content,
                "size": len(content.encode("utf-8")),
                "encoding": "utf-8",
            }
        return ok(with_workspace(payload, workspace))
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
