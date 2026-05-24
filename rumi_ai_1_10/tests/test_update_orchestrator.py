from __future__ import annotations

from pathlib import Path

from core_runtime.update.core_update_manager import CoreUpdateManager, CoreUpdateError
from core_runtime.update.models import CoreUpdateResult, PackUpdateCheck, PackUpdateResult
from core_runtime.update.update_orchestrator import UpdateOrchestrator


def test_core_update_rejects_pack_paths(tmp_path):
    base = tmp_path / "runtime"
    extracted = tmp_path / "bundle"
    extracted.mkdir()
    (extracted / "pyproject.toml").write_text('[project]\nversion = "1.11.0"\n', encoding="utf-8")
    (extracted / "packs").mkdir()
    (extracted / "packs" / "defaultspack.txt").write_text("bad", encoding="utf-8")
    manager = CoreUpdateManager(base_dir=base, user_data_dir=tmp_path / "user_data")

    try:
        manager._validate_extracted_core(extracted)
    except CoreUpdateError as exc:
        assert "protected path" in str(exc)
    else:
        raise AssertionError("core update accepted protected packs path")


def test_core_update_rejects_top_level_protected_file(tmp_path):
    base = tmp_path / "runtime"
    extracted = tmp_path / "bundle"
    extracted.mkdir()
    (extracted / "pyproject.toml").write_text('[project]\nversion = "1.11.0"\n', encoding="utf-8")
    (extracted / "pack_state").write_text("bad", encoding="utf-8")
    manager = CoreUpdateManager(base_dir=base, user_data_dir=tmp_path / "user_data")

    try:
        manager._validate_extracted_core(extracted)
    except CoreUpdateError as exc:
        assert "protected path" in str(exc)
    else:
        raise AssertionError("core update accepted protected root file")


def test_core_update_rejects_index_bundle_version_mismatch(tmp_path):
    base = tmp_path / "runtime"
    extracted = tmp_path / "bundle"
    extracted.mkdir()
    (extracted / "pyproject.toml").write_text('[project]\nversion = "1.10.0"\n', encoding="utf-8")
    manager = CoreUpdateManager(base_dir=base, user_data_dir=tmp_path / "user_data")

    try:
        manager._validate_extracted_core(extracted, expected_version="1.11.0")
    except CoreUpdateError as exc:
        assert "version mismatch" in str(exc)
    else:
        raise AssertionError("core update accepted mismatched bundle version")


def test_viewer_update_api_is_informational_and_does_not_touch_packs(tmp_path):
    packs = tmp_path / "user_data" / "packs"
    packs.mkdir(parents=True)
    before = sorted(packs.iterdir())

    result = UpdateOrchestrator().viewer_status()

    assert result["target"] == "viewer"
    assert result["rollback_available"] is False
    assert sorted(packs.iterdir()) == before


def test_layered_auto_update_runner_uses_pack_state_settings():
    class FakePackManager:
        def __init__(self):
            self.written = None

        def read_update_preferences(self):
            return {
                "auto_update": {
                    "viewer": True,
                    "core": True,
                    "official_packs": True,
                    "third_party_packs": True,
                },
                "channels": {"viewer": "stable", "core": "stable", "packs": "stable"},
                "check_interval_hours": 24,
                "last_checked_at": None,
                "last_results": [],
                "updated_at": None,
            }

        def write_update_preferences(self, settings):
            self.written = settings
            return settings

        def _auto_update_due(self, settings):
            return True

        def check_all(self, channel="stable"):
            return [
                PackUpdateCheck(
                    target="pack:defaultspack",
                    pack_id="defaultspack",
                    current_version="2.4.1",
                    latest_version="2.5.0",
                    update_available=True,
                )
            ]

        def apply_pack(self, pack_id, version=None, channel="stable", force=False):
            return PackUpdateResult(
                target=f"pack:{pack_id}",
                pack_id=pack_id,
                current_version="2.4.1",
                latest_version="2.5.0",
                applied=True,
                staged=True,
            )

    class FakeCoreManager:
        def check_core(self, channel="stable"):
            return CoreUpdateResult(
                target="core",
                current_version="1.10.0",
                latest_version="1.11.0",
                update_available=True,
            )

        def apply_core(self, version=None, channel="stable", force=False):
            return CoreUpdateResult(
                target="core",
                current_version="1.10.0",
                latest_version="1.11.0",
                applied=True,
                restart_required=True,
            )

    pack_manager = FakePackManager()
    result = UpdateOrchestrator(pack_manager=pack_manager, core_manager=FakeCoreManager()).run_auto_updates_once(
        force=True
    )

    statuses = {item["target"]: item["status"] for item in result.results}
    assert result.due is True
    assert result.enabled_targets == ["viewer", "core", "official_packs", "third_party_packs"]
    assert statuses["viewer"] == "handled_by_tauri"
    assert statuses["core"] == "applied"
    assert statuses["pack:defaultspack"] == "applied"
    assert statuses["third_party_packs"] == "manual_required"
    assert pack_manager.written["last_checked_at"] == result.checked_at
