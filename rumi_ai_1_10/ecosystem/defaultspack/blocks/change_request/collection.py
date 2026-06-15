from __future__ import annotations

from blocks._common import error, ok
from blocks.coding._workspace import resolve_workspace, workspace_error_response
from domain.change_request import ChangeRequestService


def run(input_data, context=None):
    input_data = input_data or {}
    method = str(input_data.get("_method") or "GET").upper()
    service = ChangeRequestService()
    try:
        if method == "GET":
            workspace = None
            if input_data.get("workspace_id") or input_data.get("workspace_root"):
                workspace = resolve_workspace(input_data, context)
            return ok(
                {
                    "change_requests": service.list(
                        workspace_root=workspace.root_path if workspace else None,
                        workspace_id=workspace.workspace_id if workspace else None,
                    )
                }
            )
        if method == "POST":
            workspace = resolve_workspace(input_data, context)
            metadata = input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {}
            record = service.create(
                workspace_root=workspace.root_path,
                workspace_id=workspace.workspace_id,
                title=input_data.get("title"),
                description=input_data.get("description"),
                metadata=metadata,
            )
            return ok(record)
        return error("unsupported method", code="METHOD_NOT_ALLOWED")
    except Exception as exc:
        workspace_error = workspace_error_response(exc, error)
        if workspace_error:
            return workspace_error
        return error(str(exc), code="CHANGE_REQUEST_ERROR")
