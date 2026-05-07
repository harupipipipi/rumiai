from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_workspace_root() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_WORKSPACE_ROOT")
    if override:
        return Path(override)
    return _pack_root() / "user_data" / "workspaces" / "default"


@dataclass(frozen=True)
class WorkspaceContext:
    real_root: Path
    workspace_id: str = "default"

    @property
    def display_root(self) -> str:
        return str(self.real_root)

    def resolve(self, path: str | os.PathLike[str]) -> Path:
        candidate = Path(path)
        resolved = candidate.resolve() if candidate.is_absolute() else (self.real_root / candidate).resolve()
        if resolved != self.real_root and self.real_root not in resolved.parents:
            raise ValueError(
                f"Path traversal detected: '{path}' resolves to '{resolved}' "
                f"which is outside workspace root '{self.real_root}'"
            )
        return resolved

    def is_inside(self, path: str | os.PathLike[str]) -> bool:
        try:
            self.resolve(path)
            return True
        except ValueError:
            return False

    def relative(self, path: str | os.PathLike[str]) -> str:
        return self.resolve(path).relative_to(self.real_root).as_posix()


def resolve_workspace_root(
    input_data: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    input_data = input_data or {}
    context = context or {}
    candidate = (
        input_data.get("workspace_root")
        or context.get("workspace_root")
        or (context.get("inputs") or {}).get("workspace_root")
        or _default_workspace_root()
    )
    root = Path(str(candidate)).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def workspace_context(
    input_data: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> WorkspaceContext:
    workspace_id = str((input_data or {}).get("workspace_id") or (context or {}).get("workspace_id") or "default")
    return WorkspaceContext(Path(resolve_workspace_root(input_data, context)), workspace_id=workspace_id)
