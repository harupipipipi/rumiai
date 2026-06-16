from __future__ import annotations

from blocks._common import error, ok
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.change_request import ChangeRequestService
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    input_data = input_data or {}
    cr_id = str(input_data.get("id") or "").strip()
    operation = "coding.change_request.commit"
    record_attempt(operation, "high", {"id": cr_id, "message": input_data.get("message")})
    if not is_server_approved(context, operation, input_data):
        invalid = approval_invalid_response(operation, input_data, error)
        if invalid:
            return invalid
        return ok(approval_required(operation, "high", args=input_data, id=cr_id, message=input_data.get("message")))
    try:
        result = ChangeRequestService().commit(cr_id, input_data)
        if result.get("committed"):
            record_execution(operation, "high", {"id": cr_id}, commit_hash=(result.get("commit") or {}).get("commit_hash"))
        else:
            record_failure(operation, "high", str(result.get("reason") or "blocked"), {"id": cr_id})
        return ok(result)
    except KeyError:
        result = error("change request not found", code="CHANGE_REQUEST_NOT_FOUND")
        result["_http_status"] = 404
        return result
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        record_failure(operation, "high", str(exc), {"id": cr_id})
        return error(str(exc), code="CHANGE_REQUEST_ERROR")
