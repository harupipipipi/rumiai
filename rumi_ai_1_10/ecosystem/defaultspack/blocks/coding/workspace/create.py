from __future__ import annotations

from blocks._common import error, ok
from domain.coding.workspace_store import WorkspaceStore


def run(input_data, context=None):
    del context
    root_path = input_data.get("root_path") or input_data.get("workspace_root")
    if not root_path:
        return error("'root_path' is required", code="INVALID_INPUT")
    try:
        record = WorkspaceStore().create(
            root_path,
            label=input_data.get("label"),
            workspace_id=input_data.get("workspace_id"),
            trusted=bool(input_data.get("trusted", False)),
            metadata=input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else None,
        )
        return ok({"workspace": record})
    except ValueError as exc:
        code = "WORKSPACE_EXISTS" if "already exists" in str(exc) else "INVALID_INPUT"
        return error(str(exc), code=code)
    except Exception as exc:
        return error(str(exc), code="WORKSPACE_CREATE_ERROR")
