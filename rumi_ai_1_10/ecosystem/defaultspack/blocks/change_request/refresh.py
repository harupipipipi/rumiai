from __future__ import annotations

from blocks._common import ok
from blocks.change_request._helpers import not_found_response, service, service_error_response


def run(input_data, context=None):
    del context
    input_data = input_data or {}
    try:
        return ok(service().refresh(str(input_data.get("id") or "")))
    except KeyError:
        return not_found_response()
    except Exception as exc:
        return service_error_response(exc)
