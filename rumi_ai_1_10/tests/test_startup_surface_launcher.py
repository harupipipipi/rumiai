from __future__ import annotations

from core_runtime.startup_surface_launcher import launch_pending_startup_profile_surface


class FakeActive:
    def __init__(self, metadata):
        self.metadata = dict(metadata)

    def get_metadata(self, key, default=None):
        return self.metadata.get(key, default)

    def set_metadata(self, key, value):
        self.metadata[key] = value


class FakeDesktopHandler:
    def __init__(self):
        self.calls = []

    def handle_execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"app": {"success": True, "status": "launched", "pid": 123}}


def test_pending_non_desktop_profile_launches_browser_surface():
    active = FakeActive(
        {
            "startup_surface_open_pending": True,
            "startup_profile_id": "default-profile",
            "startup_base_pack": "defaultspack",
            "startup_profile_surfaces": {"preferred": "cli", "enabled": ["cli"]},
        }
    )
    handler = FakeDesktopHandler()

    result = launch_pending_startup_profile_surface(
        active_manager=active,
        desktop_handler=handler,
    )

    assert result["launched"] is True
    assert result["surface"] == "browser"
    assert active.metadata["startup_surface_open_pending"] is False
    call = handler.calls[0]
    assert call["principal_id"] == "defaultspack"
    assert call["args"]["action"] == "launch"
    assert call["args"]["env"]["RUMI_DEFAULTSPACK_SURFACE"] == "browser"


def test_pending_desktop_profile_launches_webview_surface():
    active = FakeActive(
        {
            "startup_surface_open_pending": True,
            "startup_profile_id": "desktop-profile",
            "startup_base_pack": "defaultspack",
            "startup_profile_surfaces": {"preferred": "desktop", "enabled": ["desktop"]},
        }
    )
    handler = FakeDesktopHandler()

    result = launch_pending_startup_profile_surface(
        active_manager=active,
        desktop_handler=handler,
    )

    assert result["launched"] is True
    assert result["surface"] == "desktop"
    assert handler.calls[0]["args"]["env"]["RUMI_DEFAULTSPACK_SURFACE"] == "webview"


def test_pending_profile_launches_graph_surface_target_pack():
    active = FakeActive(
        {
            "startup_surface_open_pending": True,
            "startup_base_pack": "defaultspack",
            "startup_profile_id": "custom",
            "startup_profile_surfaces": {"preferred": "browser", "enabled": ["browser"]},
            "startup_surface_launch_target": {
                "kind": "desktop_app",
                "pack_id": "frontendpack",
                "principal_id": "frontendpack",
                "surface": "browser",
                "env": {"FRONTENDPACK_SURFACE": "web"},
                "source": "capability_graph",
            },
        }
    )
    handler = FakeDesktopHandler()

    result = launch_pending_startup_profile_surface(
        active_manager=active,
        desktop_handler=handler,
    )

    assert result["launched"] is True
    assert result["pack_id"] == "frontendpack"
    call = handler.calls[0]
    assert call["principal_id"] == "frontendpack"
    assert call["args"]["pack_id"] == "frontendpack"
    assert call["grant_config"]["allowed_packs"] == ["frontendpack"]
    assert call["args"]["env"]["FRONTENDPACK_SURFACE"] == "web"


def test_non_pending_surface_launch_is_noop():
    active = FakeActive({"startup_surface_open_pending": False})

    result = launch_pending_startup_profile_surface(
        active_manager=active,
        desktop_handler=FakeDesktopHandler(),
    )

    assert result == {"launched": False, "reason": "not_pending"}
