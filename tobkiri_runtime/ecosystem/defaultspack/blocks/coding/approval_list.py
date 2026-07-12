"""List local coding approval requests."""

from blocks._common import error, ok
from domain.safety.approval import list_approval_requests


def run(input_data, context=None):
    del context
    try:
        status = str(input_data.get("status") or "").strip() or None
        include_expired = input_data.get("include_expired", True) is not False
        limit = int(input_data.get("limit", 100))
        requests = list_approval_requests(status=status, include_expired=include_expired, limit=limit)
        pending = [item for item in requests if item.get("status") == "pending"]
        return ok({"requests": requests, "pending": pending, "count": len(requests)})
    except Exception as exc:
        return error(str(exc), code="APPROVAL_LIST_ERROR")
