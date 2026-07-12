from __future__ import annotations

from domain.coding.workspace_resolver import WorkspaceResolution
from domain.coding.workspace_store import WorkspaceStore, normalize_workspace_root


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


def require_registered_trusted_workspace(
    resolution: WorkspaceResolution,
    operation: str | None = None,
    store: WorkspaceStore | None = None,
) -> WorkspaceResolution:
    """Return a trusted registered workspace resolution or raise.

    Some operations copy or enumerate a broad portion of the workspace. For
    those, legacy arbitrary ``workspace_root`` inputs are too permissive; the
    root must correspond to a workspace record that the user explicitly
    trusted.
    """
    if resolution.uses_workspace_id:
        require_trusted_workspace(resolution, operation=operation)
        return resolution

    store = store or WorkspaceStore()
    record = store.find_by_root(resolution.root_path)
    if record is None:
        suffix = f" for {operation}" if operation else ""
        raise WorkspaceTrustRequired("registered trusted workspace required" + suffix)

    root_path = normalize_workspace_root(record.get("root_path"))
    registered = WorkspaceResolution(
        root_path=root_path,
        workspace_id=record.get("workspace_id"),
        label=record.get("label"),
        trusted=bool(record.get("trusted", False)),
        trust_granted_at=record.get("trust_granted_at"),
        last_used_at=record.get("last_used_at"),
        metadata=record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
        record=record,
        source="registered_root",
    )
    require_trusted_workspace(registered, operation=operation)
    return registered
