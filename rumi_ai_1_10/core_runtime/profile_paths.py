from __future__ import annotations

import json
import os
from pathlib import Path

from .profile_workspace import ProfileWorkspaceManager, validate_profile_id


def _default_user_data_root() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    configured = os.environ.get("RUMI_USER_DATA")
    return Path(configured) if configured else base_dir / "user_data"


def _settings_path(user_data_root: Path) -> Path:
    return user_data_root / "settings" / "startup_profiles.json"


def active_profile_id(user_data_root: Path | None = None) -> str | None:
    root = Path(user_data_root) if user_data_root is not None else _default_user_data_root()
    active_path = root / "profiles" / "active_profile.json"
    for path in (active_path, _settings_path(root)):
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidate = raw.get("active_profile_id") if isinstance(raw, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            return validate_profile_id(candidate)
    return None


def profile_user_data_dir(profile_id: str, user_data_root: Path | None = None) -> Path:
    return ProfileWorkspaceManager(user_data_root).profile_user_data_dir(profile_id)


def profile_database_path(profile_id: str, user_data_root: Path | None = None) -> Path:
    return ProfileWorkspaceManager(user_data_root).profile_database_path(profile_id)


def resolve_runtime_user_data_dir(
    *,
    profile_id: str | None = None,
    fallback_to_legacy: bool = True,
) -> Path:
    root = _default_user_data_root()
    resolved_profile_id = profile_id or active_profile_id(root)
    if resolved_profile_id:
        return profile_user_data_dir(resolved_profile_id, root)
    if fallback_to_legacy:
        return root
    raise ValueError("No active profile_id is available")


def resolve_runtime_database_path(
    *,
    profile_id: str | None = None,
    fallback_to_legacy: bool = True,
) -> Path:
    root = _default_user_data_root()
    resolved_profile_id = profile_id or active_profile_id(root)
    if resolved_profile_id:
        return profile_database_path(resolved_profile_id, root)
    if fallback_to_legacy:
        return root / "rumi.sqlite"
    raise ValueError("No active profile_id is available")
