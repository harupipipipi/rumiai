from __future__ import annotations

from blocks._common import error, ok
from domain.coding.workspace_store import WorkspaceStore


def run(input_data, context=None):
    del context
    workspace_id = input_data.get("workspace_id")
    if not workspace_id:
        return error("'workspace_id' is required", code="INVALID_INPUT")
    try:
        record = WorkspaceStore().get(str(workspace_id))
        if record is None:
            return error("workspace not found: " + str(workspace_id), code="WORKSPACE_NOT_FOUND")
        return ok({"workspace": record})
    except Exception as exc:
        return error(str(exc), code="WORKSPACE_GET_ERROR")
