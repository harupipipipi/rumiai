from __future__ import annotations

from blocks._common import error, ok
from domain.change_request import ChangeRequestService


def run(input_data, context=None):
    del context
    input_data = input_data or {}
    cr_id = str(input_data.get("id") or "").strip()
    comment_id = str(input_data.get("comment_id") or input_data.get("thread_id") or "").strip()
    method = str(input_data.get("_method") or ("PATCH" if comment_id else "GET")).upper()
    service = ChangeRequestService()
    try:
        if method == "GET":
            record = service.get(cr_id)
            if record is None:
                result = error("change request not found", code="CHANGE_REQUEST_NOT_FOUND")
                result["_http_status"] = 404
                return result
            if comment_id:
                comments = record.get("comments") if isinstance(record.get("comments"), list) else []
                for comment in comments:
                    if isinstance(comment, dict) and comment.get("id") == comment_id:
                        return ok({"comment": comment, "change_request": record})
                result = error("review comment not found", code="CHANGE_REQUEST_COMMENT_NOT_FOUND")
                result["_http_status"] = 404
                return result
            return ok(
                {
                    "change_request": record,
                    "comments": record.get("comments") or [],
                    "review_threads": record.get("review_threads") or [],
                }
            )
        if method == "POST":
            return ok(service.add_comment(cr_id, input_data))
        if method in {"PATCH", "PUT"}:
            if not comment_id:
                return error("'comment_id' is required", code="INVALID_INPUT")
            return ok(service.update_comment(cr_id, comment_id, input_data))
        return error("unsupported method", code="METHOD_NOT_ALLOWED")
    except KeyError:
        result = error("change request or review comment not found", code="CHANGE_REQUEST_NOT_FOUND")
        result["_http_status"] = 404
        return result
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="CHANGE_REQUEST_ERROR")
