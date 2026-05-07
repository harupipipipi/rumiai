"""defaults.coding.git_commit — Gitコミットブロック"""

from blocks._common import ok, error
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.coding.git_ops import GitOps
from domain.safety.audit import record_attempt, record_execution, record_failure


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

    operation = "git.commit"
    record_attempt(operation, "high", {"message": message})
    if not is_server_approved(context, operation, input_data):
        invalid = approval_invalid_response(operation, input_data, error)
        if invalid:
            return invalid
        return ok(approval_required(operation, "high", args=input_data, message=message))

    try:
        git = GitOps(input_data.get("workspace_root"))
        result = git.commit(message, all_tracked=bool(input_data.get("all_tracked", False)))
        record_execution(operation, "high", {"message": message}, commit_hash=result.get("commit_hash"))
        return ok(result)
    except Exception as e:
        record_failure(operation, "high", str(e), {"message": message})
        return error(str(e), code="GIT_ERROR")
