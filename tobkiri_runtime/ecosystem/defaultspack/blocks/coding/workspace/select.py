from __future__ import annotations

from blocks._common import error, ok
from domain.coding.workspace_store import WorkspaceStore


def run(input_data, context=None):
    del context
    workspace_id = input_data.get("workspace_id")
    if not workspace_id:
        return error("'workspace_id' is required", code="INVALID_INPUT")
    try:
        record = WorkspaceStore().select(str(workspace_id))
        return ok({"workspace": record, "selected_workspace_id": record["workspace_id"]})
    except KeyError:
        return error("workspace not found: " + str(workspace_id), code="WORKSPACE_NOT_FOUND")
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="WORKSPACE_SELECT_ERROR")
