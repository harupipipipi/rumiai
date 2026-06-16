from __future__ import annotations

from blocks._common import error, ok
from domain.change_request import ChangeRequestService


def run(input_data, context=None):
    del context
    input_data = input_data or {}
    cr_id = str(input_data.get("id") or "").strip()
    method = str(input_data.get("_method") or "GET").upper()
    service = ChangeRequestService()
    try:
        if method == "GET":
            record = service.get(cr_id)
            if record is None:
                result = error("change request not found", code="CHANGE_REQUEST_NOT_FOUND")
                result["_http_status"] = 404
                return result
            return ok({"change_request": record, "viewed_files": record.get("viewed_files") or {}})
        if method in {"POST", "PATCH", "PUT"}:
            return ok(service.set_viewed_file(cr_id, input_data))
        return error("unsupported method", code="METHOD_NOT_ALLOWED")
    except KeyError:
        result = error("change request not found", code="CHANGE_REQUEST_NOT_FOUND")
        result["_http_status"] = 404
        return result
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="CHANGE_REQUEST_ERROR")
