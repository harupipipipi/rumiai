"""defaults.coding.git_commit — Gitコミットブロック"""

from blocks._common import ok, error
from blocks.coding._approval import approval_required, is_server_approved
from domain.coding.git_ops import GitOps


def run(input_data, context=None):
    """コミットを実行する。

    input_data:
        message (str): コミットメッセージ

    returns:
        {"status":"ok","data":{"commit_hash":str,"message":str}}
    """
    message = input_data.get("message")
    if not message:
        return error("'message' is required", code="INVALID_INPUT")

    if not is_server_approved(context):
        return ok(approval_required("git.commit", "high", message=message))

    try:
        git = GitOps(input_data.get("workspace_root"))
        result = git.commit(message, all_tracked=bool(input_data.get("all_tracked", False)))
        return ok(result)
    except Exception as e:
        return error(str(e), code="GIT_ERROR")
