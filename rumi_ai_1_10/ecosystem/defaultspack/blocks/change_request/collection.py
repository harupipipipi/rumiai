from __future__ import annotations

from blocks._common import error, ok
from blocks.change_request._helpers import service, service_error_response
from blocks.coding._workspace import resolve_registered_workspace, workspace_error_response


def run(input_data, context=None):
    input_data = input_data or {}
    method = str(input_data.get("_method") or "GET").upper()
    change_requests = service()
    try:
        if method == "GET":
            workspace = None
            if input_data.get("workspace_id") or input_data.get("workspace_root"):
                workspace = resolve_registered_workspace(input_data, context, operation="list change requests")
            return ok(
                {
                    "change_requests": change_requests.list(
                        workspace_root=workspace.root_path if workspace else None,
                        workspace_id=workspace.workspace_id if workspace else None,
                    )
                }
            )
        if method == "POST":
            workspace = resolve_registered_workspace(input_data, context, operation="create change request")
            metadata = input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {}
            record = change_requests.create(
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
        return service_error_response(exc)
