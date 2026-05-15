from __future__ import annotations

from blocks._common import error, ok
from domain.coding.workspace_store import WorkspaceStore


def run(input_data, context=None):
    del input_data, context
    try:
        store = WorkspaceStore()
        return ok({
            "workspaces": store.list(),
            "selected_workspace_id": store.selected_workspace_id(),
        })
    except Exception as exc:
        return error(str(exc), code="WORKSPACE_LIST_ERROR")
