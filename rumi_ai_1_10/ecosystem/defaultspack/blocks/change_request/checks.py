from __future__ import annotations

from blocks._common import error, ok
from blocks.change_request._helpers import invalid_input_response, not_found_response, service, service_error_response


def run(input_data, context=None):
    del context
    input_data = input_data or {}
    cr_id = str(input_data.get("id") or "").strip()
    check_id = str(input_data.get("check_id") or "").strip()
    method = str(input_data.get("_method") or "GET").upper()
    action = str(input_data.get("action") or "").strip().lower().replace("-", "_")
    change_requests = service()
    try:
        if method == "GET":
            if check_id:
                return ok(change_requests.get_check(cr_id, check_id))
            return ok(change_requests.list_checks(cr_id))
        if method == "POST":
            if action in {"suggest", "suggested", "suggested_checks"}:
                payload = change_requests.list_checks(cr_id)
                return ok({"suggested_checks": payload.get("suggested_checks") or [], **payload})
            return ok(change_requests.run_check(cr_id, input_data))
        return error("unsupported method", code="METHOD_NOT_ALLOWED")
    except KeyError:
        return not_found_response("change request check not found", code="CHANGE_REQUEST_CHECK_NOT_FOUND")
    except ValueError as exc:
        return invalid_input_response(exc)
    except Exception as exc:
        return service_error_response(exc)
