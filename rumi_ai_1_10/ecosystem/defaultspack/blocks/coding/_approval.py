"""Server-side approval helpers for coding blocks."""


def is_server_approved(context=None):
    """Return True only for approval state supplied by trusted server code."""
    if not isinstance(context, dict):
        return False
    return bool(context.get("_tool_server_approved"))


def approval_required(operation, risk_level="high", **details):
    payload = {
        "approval_required": True,
        "risk_level": risk_level,
        "operation": operation,
    }
    payload.update(details)
    return payload
