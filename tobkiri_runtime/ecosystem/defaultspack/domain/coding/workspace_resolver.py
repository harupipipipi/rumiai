from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.coding.workspace_store import WorkspaceStore, normalize_workspace_root


class WorkspaceResolutionError(Exception):
    code = "WORKSPACE_ERROR"


class WorkspaceNotFoundError(WorkspaceResolutionError):
    code = "WORKSPACE_NOT_FOUND"


class WorkspacePathError(WorkspaceResolutionError):
    code = "WORKSPACE_INVALID"


@dataclass(frozen=True)
class WorkspaceResolution:
    root_path: str
    workspace_id: str | None = None
    label: str | None = None
    trusted: bool = False
    trust_granted_at: str | None = None
    last_used_at: str | None = None
    metadata: dict[str, Any] | None = None
    record: dict[str, Any] | None = None
    source: str = "cwd"

    @property
    def root(self) -> str:
        return self.root_path

    @property
    def uses_workspace_id(self) -> bool:
        return bool(self.workspace_id)


def _value_for(key: str, input_data: dict[str, Any], context: dict[str, Any]) -> Any:
    value = input_data.get(key)
    if value not in (None, ""):
        return value
    value = context.get(key)
    if value not in (None, ""):
        return value
    nested_inputs = context.get("inputs")
    if isinstance(nested_inputs, dict):
        value = nested_inputs.get(key)
        if value not in (None, ""):
            return value
    profile_policy = context.get("profile_policy")
    if isinstance(profile_policy, dict):
        value = profile_policy.get(key)
        if value not in (None, ""):
            return value
    return None


def _legacy_root(candidate: Any) -> str:
    if candidate in (None, ""):
        return os.path.realpath(os.getcwd())
    path = Path(str(candidate)).expanduser()
    return os.path.realpath(str(path))


class WorkspaceResolver:
    def __init__(self, store: WorkspaceStore | None = None) -> None:
        self._store = store or WorkspaceStore()

    @property
    def store(self) -> WorkspaceStore:
        return self._store

    def resolve(
        self,
        input_data: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        *,
        allow_cwd_fallback: bool = False,
        touch: bool = True,
    ) -> WorkspaceResolution:
        input_data = input_data or {}
        context = context or {}
        workspace_id = _value_for("workspace_id", input_data, context)
        if workspace_id:
            return self._resolve_workspace_id(str(workspace_id), touch=touch)
        workspace_root = _value_for("workspace_root", input_data, context)
        if not workspace_root:
            workspace_root = _value_for("root", input_data, context)
        if workspace_root:
            return WorkspaceResolution(root_path=_legacy_root(workspace_root), source="workspace_root")
        cwd = _value_for("cwd", input_data, context) if allow_cwd_fallback else None
        if cwd:
            return WorkspaceResolution(root_path=_legacy_root(cwd), source="cwd")
        return WorkspaceResolution(root_path=_legacy_root(None), source="cwd")

    def _resolve_workspace_id(self, workspace_id: str, *, touch: bool) -> WorkspaceResolution:
        record = self._store.get(workspace_id)
        if record is None:
            raise WorkspaceNotFoundError("workspace not found: " + workspace_id)
        try:
            root_path = normalize_workspace_root(record.get("root_path"))
        except ValueError as exc:
            raise WorkspacePathError(str(exc)) from exc
        if touch:
            touched = self._store.touch(workspace_id)
            if touched is not None:
                record = touched
        return WorkspaceResolution(
            root_path=root_path,
            workspace_id=record.get("workspace_id") or workspace_id,
            label=record.get("label"),
            trusted=bool(record.get("trusted", False)),
            trust_granted_at=record.get("trust_granted_at"),
            last_used_at=record.get("last_used_at"),
            metadata=record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
            record=record,
            source="workspace_id",
        )
