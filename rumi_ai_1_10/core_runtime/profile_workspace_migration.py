from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .profile_workspace import ProfileWorkspaceManager


MIGRATION_VERSION = 1


class ProfileWorkspaceMigration:
    def __init__(self, user_data_root: Path | None = None) -> None:
        self.workspace_manager = ProfileWorkspaceManager(user_data_root)
        self.user_data_root = self.workspace_manager.user_data_root

    @property
    def legacy_startup_profiles_path(self) -> Path:
        return self.user_data_root / "settings" / "startup_profiles.json"

    @property
    def migration_state_path(self) -> Path:
        return self.user_data_root / "profiles" / ".migration_state.json"

    @property
    def active_profile_path(self) -> Path:
        return self.user_data_root / "profiles" / "active_profile.json"

    def migrate(self) -> dict[str, Any]:
        profiles_root = self.user_data_root / "profiles"
        profiles_root.mkdir(parents=True, exist_ok=True)
        state = self._read_json(self.legacy_startup_profiles_path)
        profiles = state.get("profiles") if isinstance(state, dict) else []
        if not isinstance(profiles, list):
            profiles = []

        profile_ids: list[str] = []
        for raw_profile in profiles:
            if not isinstance(raw_profile, dict):
                continue
            profile_id = str(raw_profile.get("profile_id") or "").strip()
            if not profile_id:
                continue
            paths = self.workspace_manager.initialize_profile_workspace(raw_profile)
            if not paths.profile_file.exists():
                self.workspace_manager.save_profile_yaml(profile_id, raw_profile)
            profile_ids.append(profile_id)

        active_profile_id = state.get("active_profile_id") if isinstance(state, dict) else None
        if isinstance(active_profile_id, str) and active_profile_id.strip():
            self._write_json_if_changed(
                self.active_profile_path,
                {"version": 1, "active_profile_id": active_profile_id.strip()},
            )

        marker = {
            "version": MIGRATION_VERSION,
            "source": "settings/startup_profiles.json",
            "migrated_at": int(time.time()),
            "profile_ids": profile_ids,
        }
        previous = self._read_json(self.migration_state_path)
        if isinstance(previous, dict) and previous.get("profile_ids") == profile_ids:
            marker["migrated_at"] = previous.get("migrated_at", marker["migrated_at"])
        self._write_json_if_changed(self.migration_state_path, marker)
        return marker

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_json_if_changed(self, path: Path, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(path)


def migrate_legacy_startup_profiles(user_data_root: Path | None = None) -> dict[str, Any]:
    return ProfileWorkspaceMigration(user_data_root).migrate()
