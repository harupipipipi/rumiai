from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core_runtime.startup_profiles import START_CONTRACT, StartupProfileManager, can_connect_ports


class _FakeActiveEcosystem:
    def __init__(self) -> None:
        self.active_pack_identity = None
        self.metadata = {}
        self.interface_overrides = {}
        self.overrides = {}

    def set_metadata(self, key, value):
        self.metadata[key] = value

    def set_interface_override(self, interface_key, pack_id):
        self.interface_overrides[interface_key] = pack_id

    def remove_interface_override(self, interface_key):
        self.interface_overrides.pop(interface_key, None)

    def set_override(self, component_type, component_id):
        self.overrides[component_type] = component_id

    def remove_override(self, component_type):
        self.overrides.pop(component_type, None)


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


@pytest.fixture(autouse=True)
def _stub_approval_manager(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "core_runtime.approval_manager.get_approval_manager",
        lambda: _FakeApprovalManager(reason_by_pack={}),
    )


def _write_pack(
    root: Path,
    pack_id: str,
    component_types: dict[str, list[str]],
    *,
    identity: str | None = None,
    enabled: bool = True,
    load_order: list[str] | None = None,
    create_component_paths: bool = True,
) -> Path:
    pack_dir = root / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    ecosystem = {
        "pack_id": pack_id,
        "pack_identity": identity or f"rumi:ecosystem/{pack_id}",
        "enabled": enabled,
        "metadata": {
            "name": pack_id,
            "description": f"{pack_id} description",
        },
        "components": {},
        "load_order": load_order or [],
    }
    for component_type, provides in component_types.items():
        component_path = f"blocks/{component_type}"
        ecosystem["components"][component_type] = {
            "type": component_type,
            "id": component_type,
            "path": component_path,
            "connectivity": {
                "provides": provides,
            },
        }
        if load_order is None:
            ecosystem["load_order"].append(f"{component_type}:{component_type}")
        if create_component_paths:
            (pack_dir / component_path).mkdir(parents=True, exist_ok=True)
    eco_path = pack_dir / "ecosystem.json"
    eco_path.write_text(json.dumps(ecosystem, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return eco_path


def test_can_connect_ports_requires_direction_and_contract_match():
    assert can_connect_ports("output", [START_CONTRACT], "input", [START_CONTRACT]) is True
    assert can_connect_ports("input", [START_CONTRACT], "input", [START_CONTRACT]) is False
    assert can_connect_ports("output", ["rumiai.slot.tool.v1"], "input", ["rumiai.slot.ai_client.v1"]) is False


def test_list_profiles_payload_builds_default_profile_and_candidates(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    defaultspack_path = _write_pack(
        eco_root,
        "defaultspack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start", "defaults.frontend.emit"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
    )
    helper_path = _write_pack(
        eco_root,
        "helperpack",
        {
            "tool": ["defaults.tool.invoke"],
        },
    )
    locations = [
        SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=defaultspack_path, pack_subdir=defaultspack_path.parent),
        SimpleNamespace(pack_id="helperpack", ecosystem_json_path=helper_path, pack_subdir=helper_path.parent),
    ]
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        payload = manager.list_profiles_payload()

    assert payload["active_profile_id"] == "default-profile"
    assert payload["profiles"][0]["standard_pack_id"] == "defaultspack"
    assert payload["profiles"][0]["slots"]["tool"] == "defaultspack"
    assert payload["catalog"]["start_node"]["ports"][0]["contracts"] == [START_CONTRACT]
    assert {candidate["pack_id"] for candidate in payload["catalog"]["slot_candidates"]["tool"]} == {
        "defaultspack",
        "helperpack",
    }
    assert payload["catalog"]["slot_candidates"]["provider"][0]["pack_id"] == "defaultspack"


def test_runtime_profile_v2_fields_are_saved_and_preserved_on_update(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    defaultspack_path = _write_pack(
        eco_root,
        "defaultspack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
    )
    locations = [
        SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=defaultspack_path, pack_subdir=defaultspack_path.parent),
    ]
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile(
            {
                "profile_id": "rumi_cli",
                "name": "Rumi CLI",
                "display_name": {"ja": "Rumi CLI", "en": "Rumi CLI"},
                "locale": "ja",
                "default_flow": "cli_session",
                "default_graph": "cli_workspace",
                "surfaces": {"preferred": "cli", "enabled": ["cli"]},
                "enabled_nodes": ["defaultspack.agent"],
                "disabled_nodes": ["defaultspack.frontend"],
                "node_settings": {"defaultspack.agent": {"model": "default"}},
                "policy": {"max_tool_calls": 3},
                "permissions": {"tools": "ask"},
            }
        )
        updated = manager.update_profile("rumi_cli", {"name": "CLI Updated"})

    profile = updated["profile"]
    assert created["profile"]["version"] == 2
    assert profile["name"] == "CLI Updated"
    assert profile["kind"] == "runtime_profile"
    assert profile["default_flow"] == "cli_session"
    assert profile["default_graph"] == "cli_workspace"
    assert profile["surfaces"] == {"preferred": "cli", "enabled": ["cli"]}
    assert profile["enabled_nodes"] == ["defaultspack.agent"]
    assert profile["disabled_nodes"] == ["defaultspack.frontend"]
    assert profile["node_settings"] == {"defaultspack.agent": {"model": "default"}}
    assert profile["policy"] == {"max_tool_calls": 3}
    assert profile["permissions"] == {"tools": "ask"}


def test_update_profile_rejects_contract_mismatch(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    defaultspack_path = _write_pack(
        eco_root,
        "defaultspack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
    )
    helper_path = _write_pack(
        eco_root,
        "frontendonly",
        {
            "frontend": ["defaults.frontend.start"],
        },
    )
    locations = [
        SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=defaultspack_path, pack_subdir=defaultspack_path.parent),
        SimpleNamespace(pack_id="frontendonly", ecosystem_json_path=helper_path, pack_subdir=helper_path.parent),
    ]
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        response = manager.update_profile(
            "default-profile",
            {
                "slots": {
                    "tool": "frontendonly",
                    "frontend": "defaultspack",
                    "ai_client": "defaultspack",
                    "memory": "defaultspack",
                    "provider": "defaultspack",
                }
            },
        )

    assert response["status_code"] == 400
    assert "does not satisfy slot 'tool'" in response["error"]


def test_update_profile_rejects_runtime_unready_candidate(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    defaultspack_path = _write_pack(
        eco_root,
        "defaultspack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
    )
    broken_tool_path = _write_pack(
        eco_root,
        "broken-tool",
        {
            "tool": ["defaults.tool.invoke"],
        },
        create_component_paths=False,
    )
    locations = [
        SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=defaultspack_path, pack_subdir=defaultspack_path.parent),
        SimpleNamespace(pack_id="broken-tool", ecosystem_json_path=broken_tool_path, pack_subdir=broken_tool_path.parent),
    ]
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        response = manager.update_profile(
            "default-profile",
            {
                "slots": {
                    "tool": "broken-tool",
                    "frontend": "defaultspack",
                    "ai_client": "defaultspack",
                    "memory": "defaultspack",
                    "provider": "defaultspack",
                }
            },
        )

    assert response["status_code"] == 400
    assert "not runtime-ready for slot 'tool'" in response["error"]
    assert "path 'blocks/tool' is missing" in response["error"]


def test_list_profiles_payload_marks_modified_packs_as_not_runtime_ready(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    defaultspack_path = _write_pack(
        eco_root,
        "defaultspack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
    )
    locations = [
        SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=defaultspack_path, pack_subdir=defaultspack_path.parent),
    ]
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")
    approval_manager = _FakeApprovalManager(reason_by_pack={"defaultspack": "modified"})

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        with patch("core_runtime.approval_manager.get_approval_manager", return_value=approval_manager):
            payload = manager.list_profiles_payload()
            response = manager.update_profile(
                "default-profile",
                {
                    "slots": {
                        "tool": "defaultspack",
                        "frontend": "defaultspack",
                        "ai_client": "defaultspack",
                        "memory": "defaultspack",
                        "provider": "defaultspack",
                    }
                },
            )

    tool_candidate = payload["catalog"]["slot_candidates"]["tool"][0]
    standard_pack = payload["catalog"]["standard_packs"][0]

    assert tool_candidate["runtime_ready"] is False
    assert "Re-approve it before launching" in tool_candidate["runtime_issues"][0]
    assert standard_pack["runtime_ready"] is False
    assert response["status_code"] == 400
    assert "Standard pack 'defaultspack' is not available" in response["error"]
    assert "Re-approve it before launching" in response["error"]


def test_delete_profile_reassigns_active_profile(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    defaultspack_path = _write_pack(
        eco_root,
        "defaultspack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
    )
    locations = [
        SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=defaultspack_path, pack_subdir=defaultspack_path.parent),
    ]
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")
    active = _FakeActiveEcosystem()

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        with patch(
            "backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager",
            return_value=active,
        ):
            created = manager.create_profile({"name": "Alt profile"})
            manager.activate_profile(created["profile"]["profile_id"])
            deleted = manager.delete_profile(created["profile"]["profile_id"])
            payload = manager.list_profiles_payload()

    assert deleted["deleted"] is True
    assert deleted["deleted_profile_id"] == created["profile"]["profile_id"]
    assert deleted["active_profile_id"] == "default-profile"
    assert payload["active_profile_id"] == "default-profile"
    assert len(payload["profiles"]) == 1
    assert active.metadata == {}
    assert active.interface_overrides == {}
    assert active.overrides == {}


def test_activate_profile_updates_saved_selection_without_mutating_runtime(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    defaultspack_path = _write_pack(
        eco_root,
        "defaultspack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
    )
    helper_path = _write_pack(
        eco_root,
        "helperpack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
    )
    locations = [
        SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=defaultspack_path, pack_subdir=defaultspack_path.parent),
        SimpleNamespace(pack_id="helperpack", ecosystem_json_path=helper_path, pack_subdir=helper_path.parent),
    ]
    active = _FakeActiveEcosystem()
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile(
            {
                "name": "Helper launch",
                "slots": {
                    "tool": "helperpack",
                    "frontend": "helperpack",
                    "ai_client": "helperpack",
                    "memory": "helperpack",
                    "provider": "helperpack",
                },
            }
        )
        with patch(
            "backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager",
            return_value=active,
        ) as mock_active_manager:
            response = manager.activate_profile(created["profile"]["profile_id"])
            payload = manager.list_profiles_payload()

    assert response["activated"] is True
    assert response["active_profile_id"] == created["profile"]["profile_id"]
    assert payload["active_profile_id"] == created["profile"]["profile_id"]
    assert active.metadata == {}
    assert active.interface_overrides == {}
    assert active.overrides == {}
    mock_active_manager.assert_not_called()


def test_launch_profile_updates_active_ecosystem_metadata_and_requests_restart(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    defaultspack_path = _write_pack(
        eco_root,
        "defaultspack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
        identity="rumi:ecosystem/defaultspack",
    )
    locations = [
        SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=defaultspack_path, pack_subdir=defaultspack_path.parent),
    ]
    active = _FakeActiveEcosystem()
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        with patch(
            "backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager",
            return_value=active,
        ):
            with patch("core_runtime.api.control_panel_handlers.request_kernel_restart") as mock_restart:
                response = manager.launch_profile("default-profile")

    assert response["launched"] is True
    assert response["restart_requested"] is True
    assert response["handoff"]["kind"] == "kernel_restart"
    assert active.active_pack_identity == "rumi:ecosystem/defaultspack"
    assert active.metadata["startup_profile_id"] == "default-profile"
    assert active.metadata["startup_launched"] is True
    assert active.metadata["startup_slot_components"]["tool"] == "defaultspack:tool:tool"
    assert active.interface_overrides["rumiai.slot.tool"] == "defaultspack"
    assert active.interface_overrides["io.http.server"] == "defaultspack"
    assert active.overrides["tool"] == "defaultspack:tool:tool"
    assert active.overrides["frontend"] == "defaultspack:frontend:frontend"
    assert active.overrides["memory"] == "defaultspack:memory:memory"
    assert active.overrides["ai_client"] == "defaultspack:ai_client:ai_client"
    mock_restart.assert_called_once_with()


def test_launch_profile_rejects_shared_runtime_component_type_conflict(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    defaultspack_path = _write_pack(
        eco_root,
        "defaultspack",
        {
            "tool": ["defaults.tool.invoke"],
            "frontend": ["defaults.frontend.start"],
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
            "memory": ["defaults.memory.store"],
        },
    )
    providerpack_path = _write_pack(
        eco_root,
        "providerpack",
        {
            "ai_client": ["defaults.ai.complete", "defaults.ai.providers"],
        },
    )
    locations = [
        SimpleNamespace(pack_id="defaultspack", ecosystem_json_path=defaultspack_path, pack_subdir=defaultspack_path.parent),
        SimpleNamespace(pack_id="providerpack", ecosystem_json_path=providerpack_path, pack_subdir=providerpack_path.parent),
    ]
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        response = manager.update_profile(
            "default-profile",
            {
                "slots": {
                    "tool": "defaultspack",
                    "frontend": "defaultspack",
                    "ai_client": "defaultspack",
                    "memory": "defaultspack",
                    "provider": "providerpack",
                }
            },
        )

    assert response["status_code"] == 400
    assert "shared component type 'ai_client'" in response["error"]
