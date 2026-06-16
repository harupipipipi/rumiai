from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.startup_profiles import StartupProfileManager


class _FakeApprovalManager:
    def __init__(self, *, reason_by_pack: dict[str, str | None]) -> None:
        self.reason_by_pack = reason_by_pack

    def get_approval(self, pack_id: str):
        if pack_id not in self.reason_by_pack:
            return None
        return object()

    def is_pack_approved_and_verified(self, pack_id: str):
        reason = self.reason_by_pack.get(pack_id)
        return (reason is None, reason)


def test_search_home_compile_preview_points_surface_launch_target_to_search_home_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo_root = Path(__file__).resolve().parent.parent
    eco_root = tmp_path / "ecosystem"
    shutil.copytree(
        repo_root / "ecosystem" / "defaultspack",
        eco_root / "defaultspack",
        ignore=shutil.ignore_patterns("node_modules", "__pycache__"),
    )
    defaultspack_manifest_path = eco_root / "defaultspack" / "ecosystem.json"
    defaultspack_manifest = json.loads(defaultspack_manifest_path.read_text(encoding="utf-8"))
    defaultspack_manifest["host_execution"] = True
    defaultspack_manifest_path.write_text(
        json.dumps(defaultspack_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
    shutil.copytree(
        repo_root / "ecosystem" / "search_home_pack",
        eco_root / "search_home_pack",
        ignore=shutil.ignore_patterns("node_modules", "__pycache__"),
    )

    manager = StartupProfileManager(
        storage_path=tmp_path / "startup_profiles.json",
        interface_registry=InterfaceRegistry(),
        approval_manager=_FakeApprovalManager(
            reason_by_pack={"defaultspack": None, "search_home_pack": None}
        ),
        ecosystem_dir=str(eco_root),
    )

    created = manager.create_profile(
        {
            "base_pack": "defaultspack",
            "name": "Search Home",
            "default_graph": "defaultspack.startup",
            "capability_profile_id": "defaultspack.startup",
            "launch_capability_graph": True,
        }
    )
    profile = dict(created["profile"])
    profile["packs"] = ["defaultspack", "search_home_pack"]
    profile["node_overrides"] = {"frontend.surface": "search_home_pack.web_surface"}

    result = manager.compile_profile_preview(profile["profile_id"], {"profile": profile})

    assert result["ok"] is True
    assert result["surface_launch_target"]["pack_id"] == "search_home_pack"
    assert result["capability_graph"]["runtime_profile"]["launch"]["surface"]["pack_id"] == "search_home_pack"
