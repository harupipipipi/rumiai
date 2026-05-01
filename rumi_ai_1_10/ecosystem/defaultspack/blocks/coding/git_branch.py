"""defaults.coding.git_branch — Git branch operations."""

from blocks._common import ok, error
from domain.coding.git_ops import GitOps


def run(input_data, context=None):
    """Read, list, switch, or create/switch git branches."""
    action = input_data.get("action", "current")
    name = input_data.get("name") or input_data.get("branch")
    create = bool(input_data.get("create", False))
    try:
        git = GitOps(input_data.get("workspace_root"))
        return ok(git.branch(action=action, name=name, create=create))
    except ValueError as e:
        return error(str(e), code="INVALID_INPUT")
    except Exception as e:
        return error(str(e), code="GIT_ERROR")
