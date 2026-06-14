from __future__ import annotations


FUNCTION_ROUTE_FORBIDDEN_ERRORS = {
    "approval_check_error",
    "caller_requires_denied",
    "grant_denied",
    "pack_not_approved",
    "permission_denied",
    "requires_denied",
    "trust_denied",
}


class APIRouteFunctionError(RuntimeError):
    def __init__(self, message: str, *, status: int, error_type: str) -> None:
        super().__init__(message)
        self.status = status
        self.error_type = error_type


def api_route_function_error_status(error_type: str) -> int | None:
    normalized = str(error_type or "").strip()
    if normalized == "function_not_found":
        return None
    if normalized == "invalid_request":
        return 400
    if normalized == "rate_limited":
        return 429
    if normalized in FUNCTION_ROUTE_FORBIDDEN_ERRORS:
        return 403
    return 500


def api_route_function_public_error(error_type: str, raw_error: str | None, safe_error: str) -> str:
    status = api_route_function_error_status(error_type)
    if status == 403:
        return "Forbidden"
    return str(raw_error or safe_error)
