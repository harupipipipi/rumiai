"""defaults.coding.file_list — ファイル一覧ブロック"""

from blocks._common import ok, error
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
        ops = FileOps(input_data.get("workspace_root"))
        files = ops.list_files(directory, recursive=recursive)
        return ok({
            "directory": directory,
            "files": files,
        })
    except NotADirectoryError as e:
        return error(str(e), code="DIR_NOT_FOUND")
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        return error(str(e), code="LIST_ERROR")
