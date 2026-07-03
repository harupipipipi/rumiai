"""Create a GitHub pull request for a pushed coding branch."""

from blocks._common import error, ok
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.github_client import GitHubClientError, GitHubWriteClient
from domain.safety.audit import record_attempt, record_execution, record_failure


OPERATION = "github.pr_create"
RISK = "high"


def _explicit_repo_and_head(input_data: dict) -> bool:
    return bool(
        str(input_data.get("repo") or input_data.get("repository") or "").strip()
        and str(input_data.get("head") or input_data.get("head_ref") or input_data.get("branch") or "").strip()
    )


def run(input_data, context=None):
    input_data = input_data or {}
    client = GitHubWriteClient()
    workspace = None
    workspace_error = None
    try:
        workspace = resolve_workspace(input_data, context, mutation=True, operation=OPERATION)
    except Exception as exc:
        workspace_error = workspace_error_response(exc, error)
        if not _explicit_repo_and_head(input_data):
            if workspace_error:
                return workspace_error
            return error(str(exc), code="WORKSPACE_ERROR")

    try:
        resolved = client.resolve_pull_request_args(
            input_data,
            cwd=workspace.root_path if workspace is not None else None,
        )
    except GitHubClientError as exc:
        return error(str(exc), code=exc.code)

    record_attempt(
        OPERATION,
        RISK,
        {
            "repo": resolved["repo"],
            "title": resolved["title"],
            "head": resolved["head"],
            "base": resolved["base"],
            "draft": resolved["draft"],
        },
    )
    approval_args = {**input_data, **resolved}
    if not is_server_approved(context, OPERATION, approval_args):
        invalid = approval_invalid_response(OPERATION, approval_args, error)
        if invalid:
            return invalid
        return ok(
            approval_required(
                OPERATION,
                RISK,
                args=approval_args,
                repo=resolved["repo"],
                title=resolved["title"],
                head=resolved["head"],
                base=resolved["base"],
                draft=resolved["draft"],
                reason="network_write",
            )
        )

    try:
        result = client.create_pull_request(**resolved, cwd=workspace.root_path if workspace is not None else None)
        record_execution(
            OPERATION,
            RISK,
            {
                "repo": resolved["repo"],
                "title": resolved["title"],
                "head": resolved["head"],
                "base": resolved["base"],
                "draft": resolved["draft"],
            },
            repo=result.get("repo"),
            number=result.get("number"),
        )
        return ok(with_workspace(result, workspace) if workspace is not None else result)
    except GitHubClientError as exc:
        record_failure(OPERATION, RISK, str(exc), {"repo": resolved["repo"], "head": resolved["head"], "base": resolved["base"]})
        return error(str(exc), code=exc.code)
    except Exception as exc:
        if workspace_error:
            return workspace_error
        record_failure(OPERATION, RISK, str(exc), {"repo": resolved["repo"], "head": resolved["head"], "base": resolved["base"]})
        return error(str(exc), code="GITHUB_PR_CREATE_ERROR")
