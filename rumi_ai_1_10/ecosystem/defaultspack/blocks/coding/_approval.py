"""Server-side approval helpers for coding blocks."""


def has_server_approval(context):
    """Return True only when server/runtime explicitly granted approval.

    Never trust client-provided request body flags for privileged operations.
    """
    if not isinstance(context, dict):
        return False
    return bool(context.get("_server_approved", False))
