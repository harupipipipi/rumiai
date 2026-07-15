from __future__ import annotations

from pathlib import Path


def seccomp_profile_available(path: str | Path | None) -> bool:
    return bool(path and Path(path).is_file())


def default_seccomp_profile_path(root: str | Path) -> Path:
    return Path(root) / "seccomp" / "default.json"
