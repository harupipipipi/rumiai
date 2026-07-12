"""defaults.coding.git_diff — Git差分取得ブロック（スタブ）"""

from blocks._common import ok, error
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
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
        workspace = resolve_workspace(input_data, context)
        git = GitOps(workspace.root_path)
        result = git.diff(ref=ref)
        return ok(with_workspace(result, workspace))
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        return error(str(e), code="GIT_ERROR")
