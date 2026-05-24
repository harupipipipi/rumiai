from __future__ import annotations

from core_runtime.api.control_panel_handlers import ControlPanelHandlersMixin


class DummyPanel(ControlPanelHandlersMixin):
    pass


class DummyOrchestrator:
    def __init__(self):
        self.applied = []

    def read_settings(self):
        return {
            "auto_update": {"viewer": False, "core": False, "official_packs": False, "third_party_packs": False},
            "channels": {"viewer": "stable", "core": "stable", "packs": "stable"},
            "check_interval_hours": 24,
            "last_checked_at": None,
            "last_results": [],
            "updated_at": None,
        }

    def write_settings(self, body):
        data = self.read_settings()
        data["auto_update"].update(body["auto_update"])
        return data

    def core_status(self):
        return {"target": "core", "current_version": "1.10.0", "latest_version": "1.10.0", "update_available": False}

    def packs_status(self):
        return {"packs": [{"target": "pack:defaultspack", "current_version": "2.4.1", "latest_version": "2.5.0", "update_available": True}]}

    def pack_apply(self, pack_id, body):
        self.applied.append((pack_id, body))
        return {"target": f"pack:{pack_id}", "applied": True, "routes_reload_recommended": True}

    def core_apply(self, body):
        return {"target": "core", "applied": True, "restart_required": True}


def test_existing_defaultspack_apply_endpoint_delegates_to_pack_update(monkeypatch):
    orchestrator = DummyOrchestrator()
    monkeypatch.setattr(
        "core_runtime.update.update_orchestrator.get_update_orchestrator",
        lambda: orchestrator,
    )

    result = DummyPanel()._panel_apply_update("defaultspack", {"force": True})

    assert result["target"] == "pack:defaultspack"
    assert orchestrator.applied == [("defaultspack", {"force": True})]


def test_aggregate_pack_target_apply_endpoint_delegates_to_pack_update(monkeypatch):
    orchestrator = DummyOrchestrator()
    monkeypatch.setattr(
        "core_runtime.update.update_orchestrator.get_update_orchestrator",
        lambda: orchestrator,
    )

    result = DummyPanel()._panel_apply_update("pack:defaultspack", {"stage_id": "stage-1"})

    assert result["target"] == "pack:defaultspack"
    assert orchestrator.applied == [("defaultspack", {"stage_id": "stage-1"})]


def test_existing_rumiai_apply_endpoint_delegates_to_core_update(monkeypatch):
    monkeypatch.setattr(
        "core_runtime.update.update_orchestrator.get_update_orchestrator",
        lambda: DummyOrchestrator(),
    )

    result = DummyPanel()._panel_apply_update("rumiai", {})

    assert result["target"] == "core"
    assert result["restart_required"] is True


def test_auto_update_settings_default_to_false_and_accept_legacy_keys(monkeypatch):
    monkeypatch.setattr(
        "core_runtime.update.update_orchestrator.get_update_orchestrator",
        lambda: DummyOrchestrator(),
    )

    settings = DummyPanel()._panel_get_update_settings()
    assert settings["auto_update"] == {
        "viewer": False,
        "core": False,
        "official_packs": False,
        "third_party_packs": False,
    }

    updated = DummyPanel()._panel_update_update_settings({"auto_update": {"defaultspack": True}})
    assert updated["auto_update"]["official_packs"] is True
