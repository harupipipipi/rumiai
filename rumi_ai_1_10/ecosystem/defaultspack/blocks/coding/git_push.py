"""defaults.coding.git_push — Gitプッシュブロック"""

from blocks._common import ok, error
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.git_ops import GitOps
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    """プッシュを実行する。

    input_data:
        remote (str, optional): リモート名（デフォルト: "origin"）
        branch (str|null, optional): ブランチ名

    returns:
        {"status":"ok","data":{"remote":str,"branch":str,"pushed":true}}
    """
    remote = input_data.get("remote", "origin")
    branch = input_data.get("branch")

    operation = "git.push"
    record_attempt(operation, "high", {"remote": remote, "branch": branch})
    try:
        workspace = resolve_workspace(input_data, context, mutation=True, operation=operation)
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        return error(str(e), code="WORKSPACE_ERROR")
    if not is_server_approved(context, operation, input_data):
        invalid = approval_invalid_response(operation, input_data, error)
        if invalid:
            return invalid
        return ok(approval_required(operation, "high", args=input_data, remote=remote, branch=branch))

    try:
        git = GitOps(workspace.root_path)
        result = git.push(remote=remote, branch=branch, dry_run=bool(input_data.get("dry_run", False)))
        record_execution(operation, "high", {"remote": remote, "branch": branch})
        return ok(with_workspace(result, workspace))
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        record_failure(operation, "high", str(e), {"remote": remote, "branch": branch})
        return error(str(e), code="GIT_ERROR")
