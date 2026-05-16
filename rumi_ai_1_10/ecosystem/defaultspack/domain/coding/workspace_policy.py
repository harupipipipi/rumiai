from __future__ import annotations

from domain.coding.workspace_resolver import WorkspaceResolution


class WorkspaceTrustRequired(PermissionError):
    code = "WORKSPACE_UNTRUSTED"


def require_trusted_workspace(resolution: WorkspaceResolution, operation: str | None = None) -> None:
    if not resolution.uses_workspace_id:
        return
    if resolution.trusted:
        return
    label = resolution.label or resolution.workspace_id or "workspace"
    suffix = f" for {operation}" if operation else ""
    raise WorkspaceTrustRequired(f"trusted workspace required{suffix}: {label}")
