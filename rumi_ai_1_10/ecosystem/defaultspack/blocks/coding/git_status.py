"""defaults.coding.git_status — Gitステータス取得ブロック（スタブ）"""

from blocks._common import ok, error
from domain.coding.git_ops import GitOps


def run(input_data, context=None):
    """Gitリポジトリのステータスを返す（スタブ）。

    input_data:
        {} (パラメータなし)

    returns:
        {"status":"ok","data":{"branch":str,"clean":bool,"staged":[str],"modified":[str],"untracked":[str]}}
    """
    try:
        git = GitOps(input_data.get("workspace_root"))
        result = git.status()
        return ok(result)
    except Exception as e:
        return error(str(e), code="GIT_ERROR")
