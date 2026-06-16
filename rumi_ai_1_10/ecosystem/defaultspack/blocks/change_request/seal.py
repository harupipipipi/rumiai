from __future__ import annotations

from blocks._common import error, ok
from domain.change_request import ChangeRequestService


def run(input_data, context=None):
    del context
    input_data = input_data or {}
    try:
        return ok({"seal": ChangeRequestService().commit_seal(str(input_data.get("id") or ""))})
    except KeyError:
        result = error("change request not found", code="CHANGE_REQUEST_NOT_FOUND")
        result["_http_status"] = 404
        return result
    except Exception as exc:
        return error(str(exc), code="CHANGE_REQUEST_ERROR")
