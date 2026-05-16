"""Read GitHub PR metadata, files, comments, and checks."""

from blocks._common import error, ok
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.coding.github_client import GitHubClientError, GitHubReadClient
from domain.safety.audit import record_attempt, record_execution, record_failure


OPERATION = "github.pr_read"
RISK = "medium"


def run(input_data, context=None):
    url = str(input_data.get("url") or input_data.get("pr_url") or "").strip()
    if not url:
        return error("'url' is required", code="INVALID_INPUT")
    record_attempt(OPERATION, RISK, {"url": url})
    if not is_server_approved(context, OPERATION, input_data):
        invalid = approval_invalid_response(OPERATION, input_data, error)
        if invalid:
            return invalid
        return ok(approval_required(OPERATION, RISK, args=input_data, url=url, reason="network"))
    try:
        result = GitHubReadClient().pr(url)
        record_execution(OPERATION, RISK, {"url": url}, repo=result.get("repo"), number=result.get("number"))
        return ok(result)
    except GitHubClientError as exc:
        record_failure(OPERATION, RISK, str(exc), {"url": url})
        return error(str(exc), code=exc.code)
    except Exception as exc:
        record_failure(OPERATION, RISK, str(exc), {"url": url})
        return error(str(exc), code="GITHUB_PR_READ_ERROR")
