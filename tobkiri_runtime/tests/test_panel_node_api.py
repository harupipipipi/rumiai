from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from core_runtime.api.control_panel_handlers import ControlPanelHandlersMixin
from core_runtime.ecosystem_nodes import EcosystemNodeRegistry
from core_runtime.profile_loader import CapabilityProfileLoader


class PanelHarness(ControlPanelHandlersMixin):
    def __init__(self, *, node_registry, profile_loader, overrides_path: Path) -> None:
        self._node_registry = node_registry
        self._profile_loader = profile_loader
        self._overrides_path = overrides_path

    def _panel_node_registry(self):
        return self._node_registry

    def _panel_profile_loader(self):
        return self._profile_loader

    def _panel_profile_node_overrides_path(self) -> Path:
        self._overrides_path.parent.mkdir(parents=True, exist_ok=True)
        return self._overrides_path


class FakeApprovalManager:
    def __init__(self, approved: set[str] | None = None) -> None:
        self.approved = approved or set()

    def is_pack_approved_and_verified(self, pack_id: str):
        if pack_id in self.approved:
            return True, None
        return False, "not_approved"


def _registry(*packs: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(packs={pack.pack_id: pack for pack in packs})


def _defaultspack_harness(tmp_path: Path) -> PanelHarness:
    defaultspack_root = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
    pack = SimpleNamespace(
        pack_id="defaultspack",
        subdir=defaultspack_root,
        path=defaultspack_root,
    )
    registry = _registry(pack)
    approval_manager = FakeApprovalManager({"defaultspack"})
    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=approval_manager,
    )
    profile_loader = CapabilityProfileLoader(
        registry=registry,
        approval_manager=approval_manager,
        shared_profiles_dir=tmp_path / "missing-user-profiles",
    )
    return PanelHarness(
        node_registry=node_registry,
        profile_loader=profile_loader,
        overrides_path=tmp_path / "settings" / "profile_node_overrides.json",
    )


def test_panel_node_catalog_returns_defaultspack_nodes(tmp_path: Path) -> None:
    panel = _defaultspack_harness(tmp_path)

    payload = panel._panel_get_nodes()

    node_ids = {node["node_id"] for node in payload["nodes"]}
    assert payload["count"] >= 7
    assert "defaultspack.agent" in node_ids
    assert "defaultspack.memory" in node_ids
    assert "defaultspack.prompt" in node_ids


def test_panel_profile_node_state_and_enable_disable_overrides(tmp_path: Path) -> None:
    panel = _defaultspack_harness(tmp_path)

    disabled = panel._panel_disable_profile_node("defaultspack.startup", "defaultspack.tool")
    state = {
        item["node_id"]: item
        for item in disabled["node_state"]
        if item["node_id"] == "defaultspack.tool"
    }

    assert disabled["enabled"] is False
    assert state["defaultspack.tool"]["enabled"] is False
    assert state["defaultspack.tool"]["status"] == "disabled"

    enabled = panel._panel_enable_profile_node("defaultspack.startup", "defaultspack.tool")
    state = {
        item["node_id"]: item
        for item in enabled["node_state"]
        if item["node_id"] == "defaultspack.tool"
    }
    assert enabled["enabled"] is True
    assert state["defaultspack.tool"]["enabled"] is True
    assert json.loads(panel._overrides_path.read_text(encoding="utf-8"))[
        "defaultspack.startup"
    ]["enabled_nodes"] == ["defaultspack.tool"]
