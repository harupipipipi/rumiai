"""defaults.coding.git_commit — Gitコミットブロック（スタブ）"""

from blocks._common import ok, error
from domain.coding.git_ops import GitOps


def run(input_data, context=None):
    """コミットを実行する（スタブ）。

    input_data:
        message (str): コミットメッセージ

    returns:
        {"status":"ok","data":{"commit_hash":str,"message":str}}
    """
    message = input_data.get("message")
    if not message:
        return error("'message' is required", code="INVALID_INPUT")

    try:
        git = GitOps()
        result = git.commit(message)
        return ok(result)
    except Exception as e:
        return error(str(e), code="GIT_ERROR")
