from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core_runtime.startup_profiles import START_CONTRACT, StartupProfileManager, can_connect_ports


class _FakeActiveEcosystem:
    def __init__(self) -> None:
        self.active_pack_identity = None
        self.metadata = {}
        self.interface_overrides = {}

    def set_metadata(self, key, value):
        self.metadata[key] = value

    def set_interface_override(self, interface_key, pack_id):
        self.interface_overrides[interface_key] = pack_id

    def remove_interface_override(self, interface_key):
        self.interface_overrides.pop(interface_key, None)


def _write_pack(root: Path, pack_id: str, component_types: dict[str, list[str]], *, identity: str | None = None) -> Path:
    pack_dir = root / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    ecosystem = {
        "pack_id": pack_id,
        "pack_identity": identity or f"rumi:ecosystem/{pack_id}",
        "metadata": {
            "name": pack_id,
            "description": f"{pack_id} description",
        },
        "components": {},
    }
    for component_type, provides in component_types.items():
        ecosystem["components"][component_type] = {
            "type": component_type,
            "id": component_type,
            "connectivity": {
                "provides": provides,
            },
        }
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


def test_launch_profile_updates_active_ecosystem_metadata(tmp_path: Path):
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
            response = manager.launch_profile("default-profile")

    assert response["launched"] is True
    assert active.active_pack_identity == "rumi:ecosystem/defaultspack"
    assert active.metadata["startup_profile_id"] == "default-profile"
    assert active.metadata["startup_launched"] is True
    assert active.interface_overrides["rumiai.slot.tool"] == "defaultspack"
    assert active.interface_overrides["io.http.server"] == "defaultspack"
