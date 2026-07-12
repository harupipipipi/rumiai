"""defaults.coding.git_status — Gitステータス取得ブロック（スタブ）"""

from blocks._common import ok, error
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.git_ops import GitOps


def run(input_data, context=None):
    """Gitリポジトリのステータスを返す（スタブ）。

    input_data:
        {} (パラメータなし)

    returns:
        {"status":"ok","data":{"branch":str,"clean":bool,"staged":[str],"modified":[str],"untracked":[str]}}
    """
    try:
        workspace = resolve_workspace(input_data, context)
        git = GitOps(workspace.root_path)
        result = git.status()
        return ok(with_workspace(result, workspace))
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        return error(str(e), code="GIT_ERROR")
