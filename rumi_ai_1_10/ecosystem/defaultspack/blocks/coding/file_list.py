"""defaults.coding.file_list — ファイル一覧ブロック"""

from blocks._common import ok, error
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.file_ops import FileOps


def run(input_data, context=None):
    """ディレクトリ内のファイル一覧を返す。

    input_data:
        directory (str, optional): 対象ディレクトリ（デフォルト: "."）
        recursive (bool, optional): 再帰的に取得するか（デフォルト: false）

    returns:
        {"status":"ok","data":{"directory":str,"files":[{"name":str,"path":str,"is_dir":bool,"size":int}]}}
    """
    directory = input_data.get("directory", ".")
    recursive = input_data.get("recursive", False)

    try:
        workspace = resolve_workspace(input_data, context, allow_cwd_fallback=True)
        ops = FileOps(workspace.root_path)
        files = ops.list_files(directory, recursive=recursive)
        return ok(with_workspace({
            "directory": directory,
            "files": files,
        }, workspace))
    except NotADirectoryError as e:
        return error(str(e), code="DIR_NOT_FOUND")
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        return error(str(e), code="LIST_ERROR")
