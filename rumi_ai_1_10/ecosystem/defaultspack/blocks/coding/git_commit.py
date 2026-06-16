"""defaults.coding.git_commit — Gitコミットブロック"""

from blocks._common import ok, error
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.git_ops import GitOps
from domain.coding.workspace_jail import WorkspacePathViolation, WorkspaceRestrictedPath
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    """コミットを実行する。

    input_data:
        message (str): コミットメッセージ
        paths (list[str]): コミット対象ファイル (optional)
        files (list[str]): paths のエイリアス (optional)
        all_tracked (bool): git add -u (optional)

    returns:
        {"status":"ok","data":{"commit_hash":str,"message":str}}
    """
    message = input_data.get("message")
    if not message:
        return error("'message' is required", code="INVALID_INPUT")

    paths = input_data.get("paths") or input_data.get("files") or None
    all_tracked = bool(input_data.get("all_tracked", False))

    if paths is not None and all_tracked:
        return error(
            "paths/files and all_tracked=True cannot be used together",
            code="INVALID_INPUT",
        )

    operation = "git.commit"
    record_attempt(operation, "high", {"message": message, "paths": paths, "all_tracked": all_tracked})
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
        return ok(approval_required(operation, "high", args=input_data, message=message))

    try:
        git = GitOps(workspace.root_path)
        result = git.commit(
            message,
            all_tracked=all_tracked,
            paths=paths,
            actor_id=input_data.get("actor_id") or input_data.get("agent_id"),
            agent_role=input_data.get("agent_role"),
            session_id=input_data.get("session_id"),
            metadata=input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else None,
        )
        record_execution(operation, "high", {"message": message, "paths": paths}, commit_hash=result.get("commit_hash"))
        return ok(with_workspace(result, workspace))
    except WorkspacePathViolation as e:
        return error(str(e), code="INVALID_INPUT")
    except WorkspaceRestrictedPath as e:
        return error(str(e), code="WORKSPACE_PATH_RESTRICTED")
    except ValueError as e:
        return error(str(e), code="INVALID_INPUT")
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        record_failure(operation, "high", str(e), {"message": message, "paths": paths})
        return error(str(e), code="GIT_ERROR")
