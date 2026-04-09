"""defaults.coding.git_push — Gitプッシュブロック（スタブ）"""

from blocks._common import ok, error
from domain.coding.git_ops import GitOps


def run(input_data, context=None):
    """プッシュを実行する（スタブ）。

    input_data:
        remote (str, optional): リモート名（デフォルト: "origin"）
        branch (str|null, optional): ブランチ名

    returns:
        {"status":"ok","data":{"remote":str,"branch":str,"pushed":true}}
    """
    remote = input_data.get("remote", "origin")
    branch = input_data.get("branch")

    try:
        git = GitOps()
        result = git.push(remote=remote, branch=branch)
        return ok(result)
    except Exception as e:
        return error(str(e), code="GIT_ERROR")
