from __future__ import annotations

from blocks._common import error, ok
from domain.change_request import ChangeRequestService


def run(input_data, context=None):
    del context
    input_data = input_data or {}
    cr_id = str(input_data.get("id") or "").strip()
    check_id = str(input_data.get("check_id") or "").strip()
    method = str(input_data.get("_method") or "GET").upper()
    action = str(input_data.get("action") or "").strip().lower().replace("-", "_")
    service = ChangeRequestService()
    try:
        if method == "GET":
            if check_id:
                return ok(service.get_check(cr_id, check_id))
            return ok(service.list_checks(cr_id))
        if method == "POST":
            if action in {"suggest", "suggested", "suggested_checks"}:
                payload = service.list_checks(cr_id)
                return ok({"suggested_checks": payload.get("suggested_checks") or [], **payload})
            return ok(service.run_check(cr_id, input_data))
        return error("unsupported method", code="METHOD_NOT_ALLOWED")
    except KeyError:
        result = error("change request check not found", code="CHANGE_REQUEST_CHECK_NOT_FOUND")
        result["_http_status"] = 404
        return result
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="CHANGE_REQUEST_ERROR")
