from __future__ import annotations

import json
from pathlib import Path

from core_runtime.profile_workspace_migration import migrate_legacy_startup_profiles


def test_legacy_startup_profiles_migrate_to_profile_yaml(tmp_path: Path):
    settings = tmp_path / "settings"
    settings.mkdir()
    (settings / "startup_profiles.json").write_text(
        json.dumps(
            {
                "version": 3,
                "active_profile_id": "default-profile",
                "profiles": [
                    {
                        "version": 3,
                        "profile_id": "default-profile",
                        "name": "Default",
                        "base_pack": "defaultspack",
                        "graph_id": "defaultspack.startup",
                        "packs": ["defaultspack"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    marker = migrate_legacy_startup_profiles(tmp_path)

    assert marker["profile_ids"] == ["default-profile"]
    assert (tmp_path / "profiles" / "default-profile" / "profile.yaml").is_file()
    active = json.loads((tmp_path / "profiles" / "active_profile.json").read_text(encoding="utf-8"))
    assert active["active_profile_id"] == "default-profile"


def test_migration_is_idempotent(tmp_path: Path):
    settings = tmp_path / "settings"
    settings.mkdir()
    (settings / "startup_profiles.json").write_text(
        json.dumps({"active_profile_id": "p1", "profiles": [{"profile_id": "p1", "base_pack": "defaultspack"}]}),
        encoding="utf-8",
    )

    first = migrate_legacy_startup_profiles(tmp_path)
    second = migrate_legacy_startup_profiles(tmp_path)

    assert second["profile_ids"] == first["profile_ids"]
    marker = json.loads((tmp_path / "profiles" / ".migration_state.json").read_text(encoding="utf-8"))
    assert marker["profile_ids"] == ["p1"]
