"""defaults.coding.git_branch — Git branch operations."""

from blocks._common import ok, error
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.git_ops import GitOps
from domain.safety.audit import record_attempt, record_execution, record_failure


def _mutation_operation(action, create):
    if action == "switch":
        return "git.branch.create" if create else "git.branch.switch"
    return ""


def run(input_data, context=None):
    """Read, list, switch, or create/switch git branches."""
    action = input_data.get("action", "current")
    name = input_data.get("name") or input_data.get("branch")
    create = bool(input_data.get("create", False))
    operation = _mutation_operation(action, create)
    audit_args = {"action": action, "branch": name, "create": create}

    if operation:
        record_attempt(operation, "high", audit_args)
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
            return ok(
                approval_required(
                    operation,
                    "high",
                    args=input_data,
                    action=action,
                    branch=name,
                    create=create,
                )
            )
    else:
        try:
            workspace = resolve_workspace(input_data, context)
        except Exception as e:
            workspace_error = workspace_error_response(e, error)
            if workspace_error:
                return workspace_error
            return error(str(e), code="WORKSPACE_ERROR")

    try:
        git = GitOps(workspace.root_path)
        result = git.branch(action=action, name=name, create=create)
        if operation:
            record_execution(operation, "high", audit_args)
        return ok(with_workspace(result, workspace))
    except ValueError as e:
        if operation:
            record_failure(operation, "high", str(e), audit_args)
        return error(str(e), code="INVALID_INPUT")
    except Exception as e:
        workspace_error = workspace_error_response(e, error)
        if workspace_error:
            return workspace_error
        if operation:
            record_failure(operation, "high", str(e), audit_args)
        return error(str(e), code="GIT_ERROR")
