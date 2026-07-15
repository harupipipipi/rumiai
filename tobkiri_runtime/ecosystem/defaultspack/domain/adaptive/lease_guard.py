from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.coding.workspace_policy import WorkspaceTrustRequired, require_registered_trusted_workspace
from domain.coding.workspace_resolver import (
    WorkspacePathError,
    WorkspaceResolution,
    WorkspaceResolutionError,
    WorkspaceResolver,
)

from .context import now_seconds
from .storage import AdaptiveStore


class AdaptiveLeaseConflict(PermissionError):
    code = "ADAPTIVE_LEASE_HELD"

    def __init__(self, message: str, *, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.details = details


def lease_workspace_binding(args: dict[str, Any] | None, ctx: dict[str, Any] | None) -> dict[str, str]:
    args = args if isinstance(args, dict) else {}
    ctx = ctx if isinstance(ctx, dict) else {}
    if not _selects_workspace(args, ctx):
        return {}
    try:
        resolution = WorkspaceResolver().resolve(args, ctx, allow_cwd_fallback=False)
        trusted = require_registered_trusted_workspace(resolution, operation="adaptive.lease")
    except WorkspaceTrustRequired as exc:
        raise AdaptiveLeaseConflict(
            str(exc),
            details={"code": exc.code, "workspace": _selector_snapshot(args, ctx)},
        ) from exc
    except (WorkspacePathError, WorkspaceResolutionError, ValueError) as exc:
        raise AdaptiveLeaseConflict(
            str(exc),
            details={"code": getattr(exc, "code", "WORKSPACE_INVALID"), "workspace": _selector_snapshot(args, ctx)},
        ) from exc
    binding = {"workspace_root": str(Path(trusted.root_path).resolve())}
    if trusted.workspace_id:
        binding["workspace_id"] = str(trusted.workspace_id)
    return binding


def enforce_adaptive_lease(
    resolution: WorkspaceResolution,
    input_data: dict[str, Any] | None,
    context: dict[str, Any] | None,
    *,
    operation: str | None,
) -> None:
    args = input_data if isinstance(input_data, dict) else {}
    ctx = context if isinstance(context, dict) else {}
    targets = _targets_for_operation(str(operation or ""), args)
    if not targets:
        return
    holder = _holder(args, ctx)
    workspace = {"workspace_root": str(Path(resolution.root_path).resolve())}
    if resolution.workspace_id:
        workspace["workspace_id"] = str(resolution.workspace_id)

    for profile_id in _candidate_profile_ids(args, ctx):
        state = AdaptiveStore(profile_id).read_json("orchestration/leases.json", {"version": 1, "leases": []})
        leases = state.get("leases") if isinstance(state, dict) else []
        if not isinstance(leases, list):
            continue
        for lease in leases:
            if not isinstance(lease, dict) or not _active(lease):
                continue
            if str(lease.get("holder") or lease.get("owner") or "") == holder:
                continue
            if not _workspace_matches(lease, workspace):
                continue
            key = _normalize_resource(lease.get("key") or lease.get("resource"))
            if any(_resources_overlap(key, target) for target in targets):
                raise AdaptiveLeaseConflict(
                    "adaptive lease is held by another holder",
                    details={
                        "profile_id": profile_id,
                        "operation": str(operation or ""),
                        "lease_id": lease.get("lease_id") or lease.get("id"),
                        "key": lease.get("key") or lease.get("resource"),
                        "holder": lease.get("holder") or lease.get("owner"),
                        "request_holder": holder,
                        "workspace_id": workspace.get("workspace_id"),
                        "workspace_root": workspace.get("workspace_root"),
                    },
                )


def _selects_workspace(args: dict[str, Any], ctx: dict[str, Any]) -> bool:
    for source in (args, ctx, ctx.get("inputs"), ctx.get("profile_policy")):
        if not isinstance(source, dict):
            continue
        if any(source.get(key) not in (None, "") for key in ("workspace_id", "workspace_root", "root")):
            return True
    return False


def _selector_snapshot(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for key in ("workspace_id", "workspace_root", "root"):
        if args.get(key) not in (None, ""):
            snapshot[key] = args.get(key)
        elif ctx.get(key) not in (None, ""):
            snapshot[key] = ctx.get(key)
    return snapshot


def _holder(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    for source in (args, ctx):
        for key in ("holder", "owner", "principal_id", "caller", "actor_id", "agent_id", "session_id"):
            value = source.get(key)
            if str(value or "").strip():
                return str(value).strip()
    return "anonymous"


def _targets_for_operation(operation: str, args: dict[str, Any]) -> list[str]:
    op = operation.lower()
    if op in {"file.write", "file.patch", "file.delete", "file.create"}:
        return [_normalize_resource(args.get("path"))]
    if op == "file.move":
        return [
            _normalize_resource(args.get("source") or args.get("from") or args.get("path")),
            _normalize_resource(args.get("destination") or args.get("to")),
        ]
    if op == "file.restore":
        paths = args.get("paths")
        if isinstance(paths, list) and paths:
            return [_normalize_resource(item) for item in paths]
        return ["."]
    if op.startswith("git.commit"):
        paths = args.get("paths") or args.get("files")
        if isinstance(paths, list) and paths:
            return [_normalize_resource(item) for item in paths]
        return ["."]
    if op.startswith(("git.", "terminal.", "rumi.log.", "file.snapshot")):
        return ["."]
    return ["."]


def _normalize_resource(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if text in {"", ".", "/", "*", "workspace", "worktree"}:
        return "."
    while text.startswith("./"):
        text = text[2:]
    return text.strip("/") or "."


def _resources_overlap(lease_key: str, target: str) -> bool:
    if lease_key == "." or target == ".":
        return True
    return lease_key == target or lease_key.startswith(target + "/") or target.startswith(lease_key + "/")


def _active(lease: dict[str, Any]) -> bool:
    if lease.get("status") != "active":
        return False
    try:
        return int(lease.get("expires_at") or 0) > now_seconds()
    except (TypeError, ValueError):
        return False


def _workspace_matches(lease: dict[str, Any], workspace: dict[str, str]) -> bool:
    lease_workspace_id = str(lease.get("workspace_id") or "").strip()
    if lease_workspace_id and workspace.get("workspace_id") and lease_workspace_id != workspace.get("workspace_id"):
        return False
    lease_root = str(lease.get("workspace_root") or "").strip()
    if lease_root:
        try:
            return str(Path(lease_root).resolve()) == workspace.get("workspace_root")
        except Exception:
            return False
    return True


def _candidate_profile_ids(args: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    try:
        from domain.adaptive.guard import _candidate_profile_ids as guard_profile_ids

        return guard_profile_ids(args, ctx)
    except Exception:
        profile_id = str(args.get("profile_id") or ctx.get("profile_id") or "default").strip() or "default"
        return [profile_id]
