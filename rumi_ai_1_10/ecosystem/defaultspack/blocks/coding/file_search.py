"""defaults.coding.file_search — ファイル検索ブロック"""

from blocks._common import ok, error
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
        ops = FileOps(input_data.get("workspace_root"))
        matches = ops.search_files(pattern, directory)
        return ok({
            "pattern": pattern,
            "matches": matches,
        })
    except NotADirectoryError as e:
        return error(str(e), code="DIR_NOT_FOUND")
    except ValueError as e:
        return error(str(e), code="PATH_TRAVERSAL")
    except Exception as e:
        return error(str(e), code="SEARCH_ERROR")
