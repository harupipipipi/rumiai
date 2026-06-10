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


class FakeGrantResult:
    def __init__(self, allowed=True, config=None):
        self.allowed = allowed
        self.config = config or {}


class FakeGrantManager:
    def __init__(self, allowed=True, config=None):
        self.result = FakeGrantResult(allowed=allowed, config=config)
        self.calls = []

    def check(self, principal_id, permission_id):
        self.calls.append((principal_id, permission_id))
        return self.result


def test_pending_non_desktop_profile_launches_browser_surface(monkeypatch):
    active = FakeActive(
        {
            "startup_surface_open_pending": True,
            "startup_profile_id": "default-profile",
            "startup_base_pack": "defaultspack",
            "startup_profile_surfaces": {"preferred": "cli", "enabled": ["cli"]},
        }
    )
    handler = FakeDesktopHandler()
    grant_manager = FakeGrantManager(config={"allowed_packs": ["defaultspack"]})
    monkeypatch.setattr(
        "core_runtime.startup_surface_launcher.get_capability_grant_manager",
        lambda: grant_manager,
    )

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


def test_pending_desktop_profile_launches_webview_surface(monkeypatch):
    active = FakeActive(
        {
            "startup_surface_open_pending": True,
            "startup_profile_id": "desktop-profile",
            "startup_base_pack": "defaultspack",
            "startup_profile_surfaces": {"preferred": "desktop", "enabled": ["desktop"]},
        }
    )
    handler = FakeDesktopHandler()
    grant_manager = FakeGrantManager(config={"allowed_packs": ["defaultspack"]})
    monkeypatch.setattr(
        "core_runtime.startup_surface_launcher.get_capability_grant_manager",
        lambda: grant_manager,
    )

    result = launch_pending_startup_profile_surface(
        active_manager=active,
        desktop_handler=handler,
    )

    assert result["launched"] is True
    assert result["surface"] == "desktop"
    assert handler.calls[0]["args"]["env"]["RUMI_DEFAULTSPACK_SURFACE"] == "webview"


def test_pending_profile_launches_graph_surface_target_pack(monkeypatch):
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
    grant_manager = FakeGrantManager(config={"allowed_packs": ["frontendpack"]})
    monkeypatch.setattr(
        "core_runtime.startup_surface_launcher.get_capability_grant_manager",
        lambda: grant_manager,
    )

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
    assert call["grant_config"]["port"] == 8765
    assert call["args"]["env"]["FRONTENDPACK_SURFACE"] == "web"


def test_surface_launch_uses_runtime_port_from_env(monkeypatch):
    monkeypatch.setenv("RUMI_PORT", "8767")
    active = FakeActive(
        {
            "startup_surface_open_pending": True,
            "startup_surface_launch_target": {
                "kind": "desktop_app",
                "pack_id": "frontendpack",
                "principal_id": "frontendpack",
                "surface": "browser",
            },
        }
    )
    handler = FakeDesktopHandler()
    grant_manager = FakeGrantManager(config={"allowed_packs": ["frontendpack"]})
    monkeypatch.setattr(
        "core_runtime.startup_surface_launcher.get_capability_grant_manager",
        lambda: grant_manager,
    )

    launch_pending_startup_profile_surface(
        active_manager=active,
        desktop_handler=handler,
    )

    assert handler.calls[0]["grant_config"]["port"] == 8767


def test_surface_launch_invalid_runtime_port_falls_back(monkeypatch):
    monkeypatch.setenv("RUMI_PORT", "not-a-port")
    active = FakeActive(
        {
            "startup_surface_open_pending": True,
            "startup_surface_launch_target": {
                "kind": "desktop_app",
                "pack_id": "frontendpack",
                "principal_id": "frontendpack",
                "surface": "browser",
            },
        }
    )
    handler = FakeDesktopHandler()
    grant_manager = FakeGrantManager(config={"allowed_packs": ["frontendpack"]})
    monkeypatch.setattr(
        "core_runtime.startup_surface_launcher.get_capability_grant_manager",
        lambda: grant_manager,
    )

    launch_pending_startup_profile_surface(
        active_manager=active,
        desktop_handler=handler,
    )

    assert handler.calls[0]["grant_config"]["port"] == 8765


def test_non_pending_surface_launch_is_noop():
    active = FakeActive({"startup_surface_open_pending": False})

    result = launch_pending_startup_profile_surface(
        active_manager=active,
        desktop_handler=FakeDesktopHandler(),
    )

    assert result == {"launched": False, "reason": "not_pending"}


def test_surface_launch_requires_desktop_execute_grant(monkeypatch):
    active = FakeActive(
        {
            "startup_surface_open_pending": True,
            "startup_surface_launch_target": {
                "kind": "desktop_app",
                "pack_id": "frontendpack",
                "principal_id": "frontendpack",
                "surface": "browser",
            },
        }
    )
    handler = FakeDesktopHandler()
    grant_manager = FakeGrantManager(allowed=False)
    monkeypatch.setattr(
        "core_runtime.startup_surface_launcher.get_capability_grant_manager",
        lambda: grant_manager,
    )

    result = launch_pending_startup_profile_surface(
        active_manager=active,
        desktop_handler=handler,
    )

    assert result["launched"] is False
    assert result["reason"] == "desktop_app_execute_not_granted"
    assert result["status_code"] == 403
    assert "desktop_app.execute not granted" in result["error"]
    assert handler.calls == []
    assert grant_manager.calls == [("frontendpack", "desktop_app.execute")]
    assert active.metadata["startup_surface_open_pending"] is False
