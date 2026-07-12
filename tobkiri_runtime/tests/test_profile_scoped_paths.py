from __future__ import annotations

import json
from pathlib import Path

from core_runtime.profile_paths import (
    active_profile_id,
    profile_database_path,
    profile_user_data_dir,
    resolve_runtime_database_path,
    resolve_runtime_user_data_dir,
)


def test_profile_scoped_path_resolvers_use_active_profile(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    active_path = tmp_path / "profiles" / "active_profile.json"
    active_path.parent.mkdir()
    active_path.write_text(json.dumps({"active_profile_id": "p1"}), encoding="utf-8")

    assert active_profile_id() == "p1"
    assert resolve_runtime_user_data_dir() == tmp_path / "profiles" / "p1" / "user_data"
    assert resolve_runtime_database_path() == tmp_path / "profiles" / "p1" / "database" / "rumi.sqlite"


def test_profile_scoped_path_resolvers_can_fallback_to_legacy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))

    assert resolve_runtime_user_data_dir() == tmp_path
    assert resolve_runtime_database_path() == tmp_path / "rumi.sqlite"


def test_profile_database_and_user_data_helpers_are_scoped(tmp_path: Path):
    assert profile_user_data_dir("p2", tmp_path) == tmp_path / "profiles" / "p2" / "user_data"
    assert profile_database_path("p2", tmp_path) == tmp_path / "profiles" / "p2" / "database" / "rumi.sqlite"
