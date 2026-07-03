from __future__ import annotations

from typing import Any

from domain.adaptive.lease_guard import AdaptiveLeaseConflict, enforce_adaptive_lease
from domain.coding.workspace_policy import (
    WorkspaceTrustRequired,
    require_registered_trusted_workspace,
    require_trusted_workspace,
)
from domain.coding.workspace_resolver import (
    WorkspaceNotFoundError,
    WorkspacePathError,
    WorkspaceResolution,
    WorkspaceResolutionError,
    WorkspaceResolver,
)


def resolve_workspace(
    input_data: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
    *,
    mutation: bool = False,
    operation: str | None = None,
    allow_cwd_fallback: bool = False,
) -> WorkspaceResolution:
    resolution = WorkspaceResolver().resolve(
        input_data,
        context,
        allow_cwd_fallback=allow_cwd_fallback,
    )
    if mutation:
        require_trusted_workspace(resolution, operation=operation)
        enforce_adaptive_lease(resolution, input_data, context, operation=operation)
    return resolution


def resolve_registered_workspace(
    input_data: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
    *,
    operation: str | None = None,
    allow_cwd_fallback: bool = False,
) -> WorkspaceResolution:
    context = context if isinstance(context, dict) else {}
    resolution = WorkspaceResolver().resolve(
        input_data,
        context,
        allow_cwd_fallback=allow_cwd_fallback,
    )
    if _allows_unregistered_workspace_root(context):
        if resolution.uses_workspace_id:
            require_trusted_workspace(resolution, operation=operation)
        return resolution
    if not resolution.uses_workspace_id:
        suffix = f" for {operation}" if operation else ""
        raise WorkspaceTrustRequired("registered trusted workspace_id required" + suffix)
    return require_registered_trusted_workspace(resolution, operation=operation)


def workspace_error_response(exc: Exception, error_func):
    if isinstance(exc, AdaptiveLeaseConflict):
        result = error_func(str(exc), code=exc.code)
        result["details"] = exc.details
        result["_http_status"] = 409
        return result
    if isinstance(exc, WorkspaceTrustRequired):
        result = error_func(str(exc), code=exc.code)
        result["_http_status"] = 403
        return result
    if isinstance(exc, WorkspaceNotFoundError):
        return error_func(str(exc), code=exc.code)
    if isinstance(exc, WorkspacePathError):
        return error_func(str(exc), code=exc.code)
    if isinstance(exc, WorkspaceResolutionError):
        return error_func(str(exc), code=exc.code)
    return None


def with_workspace(data: dict[str, Any], resolution: WorkspaceResolution) -> dict[str, Any]:
    payload = dict(data)
    payload.setdefault("workspace_id", resolution.workspace_id)
    payload.setdefault("workspace_root", resolution.root_path)
    payload.setdefault("root", resolution.root_path)
    return payload


def _allows_unregistered_workspace_root(context: dict[str, Any]) -> bool:
    return bool(
        context.get("trusted_internal")
        or context.get("_trusted_internal")
        or context.get("allow_unregistered_workspace_root")
    )
