from __future__ import annotations

from blocks._common import error
from domain.change_request import ChangeRequestService


def service() -> ChangeRequestService:
    return ChangeRequestService()


def not_found_response(
    message: str = "change request not found",
    *,
    code: str = "CHANGE_REQUEST_NOT_FOUND",
):
    result = error(message, code=code)
    result["_http_status"] = 404
    return result


def invalid_input_response(exc: ValueError):
    return error(str(exc), code="INVALID_INPUT")


def service_error_response(exc: Exception):
    return error(str(exc), code="CHANGE_REQUEST_ERROR")
