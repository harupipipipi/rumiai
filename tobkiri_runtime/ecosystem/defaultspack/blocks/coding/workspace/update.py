from __future__ import annotations

from blocks._common import error, ok
from domain.coding.workspace_store import WorkspaceStore


def run(input_data, context=None):
    del context
    workspace_id = input_data.get("workspace_id")
    if not workspace_id:
        return error("'workspace_id' is required", code="INVALID_INPUT")
    updates = {}
    for key in ("label", "root_path", "metadata"):
        if key in input_data:
            updates[key] = input_data.get(key)
    if "workspace_root" in input_data and "root_path" not in updates:
        updates["root_path"] = input_data.get("workspace_root")
    if not updates:
        return error("no workspace updates provided", code="INVALID_INPUT")
    try:
        return ok({"workspace": WorkspaceStore().update(str(workspace_id), updates)})
    except KeyError:
        return error("workspace not found: " + str(workspace_id), code="WORKSPACE_NOT_FOUND")
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        return error(str(exc), code="WORKSPACE_UPDATE_ERROR")
