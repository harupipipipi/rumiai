"""defaults.coding.git_diff — Git差分取得ブロック（スタブ）"""

from blocks._common import ok, error
from domain.coding.git_ops import GitOps


def run(input_data, context=None):
    """Git差分を返す（スタブ）。

    input_data:
        ref (str|null, optional): 比較先リファレンス

    returns:
        {"status":"ok","data":{"diff":str,"files_changed":int}}
    """
    ref = input_data.get("ref")

    try:
        git = GitOps(input_data.get("workspace_root"))
        result = git.diff(ref=ref)
        return ok(result)
    except Exception as e:
        return error(str(e), code="GIT_ERROR")
