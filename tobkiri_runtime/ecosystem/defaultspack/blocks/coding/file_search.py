"""defaults.coding.file_search — ファイル検索ブロック"""

from blocks._common import ok, error
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    """globパターンでファイルを検索する。

    input_data:
        pattern (str): 検索パターン（glob形式）
        directory (str, optional): 検索ディレクトリ（デフォルト: "."）

    returns:
        {"status":"ok","data":{"pattern":str,"matches":[str]}}
    """
    pattern = input_data.get("pattern")
    if not pattern:
        return error("'pattern' is required", code="INVALID_INPUT")

    directory = input_data.get("directory", ".")

    try:
        workspace = resolve_workspace(input_data, context, allow_cwd_fallback=True)
        ops = FileOps(workspace.root_path)
        matches = ops.search_files(pattern, directory)
        return ok(with_workspace({
            "pattern": pattern,
            "matches": matches,
        }, workspace))
    except NotADirectoryError as e:
        return error(str(e), code="DIR_NOT_FOUND")
    except PermissionError as e:
        return error(str(e), code="PATH_RESTRICTED")
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        return error(str(e), code="SEARCH_ERROR")
