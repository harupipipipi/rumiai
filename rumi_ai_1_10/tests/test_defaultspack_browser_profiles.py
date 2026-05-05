from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_browser_profile_manager_persists_managed_chromium_profiles(tmp_path):
    from domain.browser.profiles import BrowserProfileManager

    manager = BrowserProfileManager(tmp_path)
    created = manager.create_profile(
        profile_id="Work Login",
        name="Work Login",
        settings={"viewport": {"width": 1280, "height": 720}},
        metadata={"purpose": "qa"},
    )

    assert created["id"] == "work-login"
    assert created["schema"] == "managed_chromium"
    assert created["kind"] == "managed_chromium"
    assert "--user-data-dir=" in " ".join(created["launch"]["args"])
    assert Path(created["user_data_dir"]).is_dir()
    assert Path(created["cache_dir"]).is_dir()
    assert manager.get_active_profile_id() == "work-login"

    reloaded = BrowserProfileManager(tmp_path)
    profile = reloaded.get_profile("work-login")
    assert profile["name"] == "Work Login"
    assert profile["settings"]["viewport"]["width"] == 1280
    assert profile["metadata"]["purpose"] == "qa"

    updated = reloaded.update_profile("work-login", {"name": "Work", "metadata": {"team": "browser"}})
    assert updated["name"] == "Work"
    assert updated["metadata"]["purpose"] == "qa"
    assert updated["metadata"]["team"] == "browser"

    reloaded.create_profile(profile_id="Other", set_active=False)
    active = reloaded.set_active_profile("other")
    assert active["active_profile_id"] == "other"
    deleted = reloaded.delete_profile("work-login")
    assert deleted["deleted"] is True
    assert {item["id"] for item in reloaded.list_profiles()} == {"other"}


def test_browser_profile_block_wraps_manager_result(tmp_path):
    from blocks.browser.profiles import run

    result = run(
        {
            "browser_root": str(tmp_path),
            "action": "create",
            "profile_id": "Research",
            "name": "Research",
        },
        {},
    )
    listed = run({"browser_root": str(tmp_path), "action": "list"}, {})

    assert result["status"] == "ok"
    assert result["data"]["profile"]["id"] == "research"
    assert listed["status"] == "ok"
    assert listed["data"]["profiles"][0]["id"] == "research"
