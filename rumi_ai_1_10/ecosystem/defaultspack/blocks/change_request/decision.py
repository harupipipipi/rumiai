from __future__ import annotations

from blocks._common import error, ok
from domain.change_request import ChangeRequestService


def run(input_data, context=None):
    del context
    input_data = input_data or {}
    try:
        return ok(ChangeRequestService().submit_decision(str(input_data.get("id") or ""), input_data))
    except KeyError:
        result = error("change request not found", code="CHANGE_REQUEST_NOT_FOUND")
        result["_http_status"] = 404
        return result
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="CHANGE_REQUEST_ERROR")
