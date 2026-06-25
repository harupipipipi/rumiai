from __future__ import annotations

from pathlib import Path


def require_workspace_root(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_dir():
        raise ValueError("workspace root must exist")
    return candidate


def require_path_within_workspace(workspace_root: str | Path, candidate: str | Path) -> Path:
    root = require_workspace_root(workspace_root)
    resolved = (root / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate).resolve()
    resolved.relative_to(root)
    return resolved
