from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import yaml

from core_runtime.startup_profiles import StartupProfileManager, PROFILE_VERSION
from core_runtime.interface_registry import InterfaceRegistry


class _FakeActiveEcosystem:
    def __init__(self) -> None:
        self.active_pack_identity = None
        self.metadata: dict = {}
        self.interface_overrides: dict = {}
        self.overrides: dict = {}

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


def _write_graph_file(pack_dir: Path, graph_id: str, nodes: list, edges: list) -> Path:
    graphs_dir = pack_dir / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    graph_data = {
        "graph_id": graph_id,
        "version": "rumi.graph.v1",
        "display_name": {"en": graph_id},
        "nodes": nodes,
        "edges": edges,
    }
    graph_file = graphs_dir / f"{graph_id.split('.')[-1]}.graph.yaml"
    graph_file.write_text(yaml.dump(graph_data, allow_unicode=True), encoding="utf-8")
    return graph_file


def _ports_for_node(node_id: str) -> list[dict]:
    ports_by_node = {
        "agent": [
            {"id": "start", "direction": "input", "standards": ["rumi.flow.start"]},
            {"id": "ai", "direction": "input", "standards": ["rumi.ai.client"]},
            {"id": "alt_ai", "direction": "input", "standards": ["rumi.ai.client"]},
            {"id": "tools", "direction": "input", "standards": ["rumi.tool.bundle"]},
            {"id": "memory", "direction": "input", "standards": ["rumi.memory.store"]},
            {"id": "prompt", "direction": "input", "standards": ["rumi.prompt.bundle"]},
        ],
        "ai_client": [{"id": "client", "direction": "output", "standards": ["rumi.ai.client"]}],
        "ai_client_2": [{"id": "client", "direction": "output", "standards": ["rumi.ai.client"]}],
        "tool": [{"id": "tools", "direction": "output", "standards": ["rumi.tool.bundle"]}],
        "memory": [{"id": "memory", "direction": "output", "standards": ["rumi.memory.store"]}],
        "prompt": [{"id": "prompt", "direction": "output", "standards": ["rumi.prompt.bundle"]}],
        "frontend": [
            {"id": "surface", "direction": "input", "standards": ["rumi.surface"]},
            {"id": "surface", "direction": "output", "standards": ["rumi.surface"]},
        ],
    }
    return ports_by_node.get(node_id, [])


def _write_node_file(pack_dir: Path, node_id: str, ref: str | None = None) -> Path:
    nodes_dir = pack_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    pack_id = pack_dir.name
    node_data = {
        "version": "rumi.node.v1",
        "nodes": [
            {
                "node_id": f"{pack_id}.{node_id}",
                "component_id": node_id,
                "display_name": {"en": node_id},
                "ports": _ports_for_node(node_id),
            }
        ],
    }
    node_file = nodes_dir / f"{node_id}.node.json"
    node_file.write_text(json.dumps(node_data, indent=2) + "\n", encoding="utf-8")
    return node_file


def _write_pack(
    root: Path,
    pack_id: str,
    *,
    enabled: bool = True,
    identity: str | None = None,
    graphs: list[dict] | None = None,
    nodes: list[str] | None = None,
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
    }
    eco_path = pack_dir / "ecosystem.json"
    eco_path.write_text(json.dumps(ecosystem, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if graphs:
        for g in graphs:
            _write_graph_file(pack_dir, g["graph_id"], g.get("nodes", []), g.get("edges", []))

    if nodes:
        for node_id in nodes:
            _write_node_file(pack_dir, node_id)

    return eco_path


def _startup_graph(pack_id: str) -> dict:
    return {
        "graph_id": f"{pack_id}.startup",
        "nodes": [
            {"id": "start", "ref": "rumi.start"},
            {"id": "ai", "ref": f"{pack_id}.ai_client"},
            {"id": "tools", "ref": f"{pack_id}.tool"},
            {"id": "memory", "ref": f"{pack_id}.memory"},
            {"id": "agent", "ref": f"{pack_id}.agent"},
            {"id": "frontend", "ref": f"{pack_id}.frontend"},
        ],
        "edges": [
            {"id": "start_to_agent", "from": "start.out", "to": "agent.start", "kind": "binding"},
            {"id": "ai_to_agent", "from": "ai.client", "to": "agent.ai", "kind": "binding"},
            {"id": "tools_to_agent", "from": "tools.tools", "to": "agent.tools", "kind": "binding"},
            {"id": "memory_to_agent", "from": "memory.memory", "to": "agent.memory", "kind": "binding"},
            {"id": "frontend_surface", "from": "frontend.surface", "to": "frontend.surface", "kind": "binding"},
        ],
    }


def _discover_locations(root: Path, pack_ids: list[str]) -> list[SimpleNamespace]:
    locations = []
    for pack_id in pack_ids:
        pack_dir = root / pack_id
        eco_path = pack_dir / "ecosystem.json"
        locations.append(
            SimpleNamespace(pack_id=pack_id, ecosystem_json_path=eco_path, pack_subdir=pack_dir)
        )
    return locations


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_create_profile_requires_base_pack(tmp_path: Path):
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")
    result = manager.create_profile({})
    assert result["status_code"] == 400
    assert "base_pack is required" in result["error"]


def test_create_profile_rejects_unavailable_base_pack(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(eco_root, "defaultspack", graphs=[_startup_graph("defaultspack")], nodes=["agent", "ai_client", "tool", "memory", "frontend"])
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        result = manager.create_profile({"base_pack": "nonexistent", "name": "Test"})

    assert result["status_code"] == 400
    assert "not available" in result["error"]


def test_create_profile_with_base_pack(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        result = manager.create_profile({"base_pack": "defaultspack", "name": "My Profile"})

    assert result["created"] is True
    profile = result["profile"]
    assert profile["version"] == PROFILE_VERSION
    assert profile["base_pack"] == "defaultspack"
    assert profile["graph_id"] == "defaultspack.startup"
    assert profile["packs"] == ["defaultspack"]
    assert profile["node_overrides"] == {}
    assert len(profile["graph_ports"]) > 0
    start_port = next(port for port in profile["graph_ports"] if port["port_key"] == "agent.start")
    assert start_port["source_node_ref"] == "rumi.start"
    assert start_port["source_port"]["standards"] == ["rumi.flow.start"]


def test_create_profile_auto_detects_graph(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        result = manager.create_profile({"base_pack": "defaultspack"})

    assert result["created"] is True
    assert result["profile"]["graph_id"] == "defaultspack.startup"


def test_create_duplicate_profile_id_rejected(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        manager.create_profile({"profile_id": "my-profile", "base_pack": "defaultspack"})
        result = manager.create_profile({"profile_id": "my-profile", "base_pack": "defaultspack"})

    assert result["status_code"] == 409


def test_list_profiles_returns_catalog_with_packs_and_graphs(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        payload = manager.list_profiles_payload()

    assert payload["active_profile_id"] is None
    assert payload["profiles"] == []
    catalog = payload["catalog"]
    assert len(catalog["packs"]) == 1
    pack = catalog["packs"][0]
    assert pack["pack_id"] == "defaultspack"
    assert len(pack["graphs"]) > 0
    assert len(pack["nodes"]) > 0
    assert any(node["node_id"] == "rumi.start" for node in pack["nodes"])


def test_default_manager_uses_rumi_user_data_and_seeds_default_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root,
        "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    user_data_dir = tmp_path / "app-data" / "user_data"
    monkeypatch.setenv("RUMI_USER_DATA", str(user_data_dir))
    manager = StartupProfileManager()

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        payload = manager.list_profiles_payload()

    assert manager.storage_path == user_data_dir / "settings" / "startup_profiles.json"
    assert payload["active_profile_id"] == "default-profile"
    assert len(payload["profiles"]) == 1
    profile = payload["profiles"][0]
    assert profile["profile_id"] == "default-profile"
    assert profile["base_pack"] == "defaultspack"
    assert profile["graph_id"] == "defaultspack.startup"
    assert any(port["port_key"] == "agent.start" for port in profile["graph_ports"])


def test_add_pack_to_profile(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    _write_pack(eco_root, "helperpack", nodes=["tool"])
    locations = _discover_locations(eco_root, ["defaultspack", "helperpack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack", "name": "Test"})
        profile_id = created["profile"]["profile_id"]
        result = manager.add_pack_to_profile(profile_id, "helperpack")

    assert result["pack_added"] == "helperpack"
    assert "helperpack" in result["profile"]["packs"]


def test_add_duplicate_pack_rejected(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        result = manager.add_pack_to_profile(profile_id, "defaultspack")

    assert result["status_code"] == 409


def test_remove_pack_from_profile(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    _write_pack(eco_root, "helperpack", nodes=["tool"])
    locations = _discover_locations(eco_root, ["defaultspack", "helperpack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        manager.add_pack_to_profile(profile_id, "helperpack")
        result = manager.remove_pack_from_profile(profile_id, "helperpack")

    assert result["pack_removed"] == "helperpack"
    assert "helperpack" not in result["profile"]["packs"]


def test_remove_base_pack_rejected(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        result = manager.remove_pack_from_profile(profile_id, "defaultspack")

    assert result["status_code"] == 400
    assert "Cannot remove the base pack" in result["error"]


def test_set_node_override(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    _write_pack(eco_root, "coolpack", nodes=["ai_client"])
    locations = _discover_locations(eco_root, ["defaultspack", "coolpack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        manager.add_pack_to_profile(profile_id, "coolpack")
        result = manager.set_node_override(profile_id, "agent.ai", "coolpack.ai_client")

    assert result["override_set"]["port_key"] == "agent.ai"
    assert result["override_set"]["node_id"] == "coolpack.ai_client"
    assert result["profile"]["node_overrides"]["agent.ai"] == "coolpack.ai_client"


def test_set_node_override_rejects_invalid_port(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    _write_pack(eco_root, "coolpack", nodes=["ai_client"])
    locations = _discover_locations(eco_root, ["defaultspack", "coolpack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        manager.add_pack_to_profile(profile_id, "coolpack")
        result = manager.set_node_override(profile_id, "invalid.port", "coolpack.ai_client")

    assert result["status_code"] == 400
    assert "not a valid graph port" in result["error"]


def test_set_node_override_rejects_unavailable_node(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        result = manager.set_node_override(profile_id, "agent.ai", "nonexistent.ai_client")

    assert result["status_code"] == 400
    assert "not available" in result["error"]


def test_set_node_override_rejects_incompatible_node_standard(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    _write_pack(eco_root, "toolpack", nodes=["tool"])
    locations = _discover_locations(eco_root, ["defaultspack", "toolpack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        manager.add_pack_to_profile(profile_id, "toolpack")
        result = manager.set_node_override(profile_id, "agent.ai", "toolpack.tool")

    assert result["status_code"] == 400
    assert "does not satisfy port 'agent.ai'" in result["error"]
    assert "rumi.ai.client" in result["error"]


def test_profile_validation_rejects_component_binding_conflict(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    conflict_graph = _startup_graph("defaultspack")
    conflict_graph["edges"].append(
        {"id": "ai_to_agent_alt", "from": "ai.client", "to": "agent.alt_ai", "kind": "binding"}
    )
    _write_pack(
        eco_root, "defaultspack",
        graphs=[conflict_graph],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    _write_pack(eco_root, "coolpack", nodes=["ai_client"])
    locations = _discover_locations(eco_root, ["defaultspack", "coolpack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        manager.add_pack_to_profile(profile_id, "coolpack")
        result = manager.set_node_override(profile_id, "agent.alt_ai", "coolpack.ai_client")

    assert result["status_code"] == 400
    assert "Component binding conflict" in result["error"]


def test_clear_node_override(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    _write_pack(eco_root, "coolpack", nodes=["ai_client"])
    locations = _discover_locations(eco_root, ["defaultspack", "coolpack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        manager.add_pack_to_profile(profile_id, "coolpack")
        manager.set_node_override(profile_id, "agent.ai", "coolpack.ai_client")
        result = manager.clear_node_override(profile_id, "agent.ai")

    assert result["override_cleared"] == "agent.ai"
    assert "agent.ai" not in result["profile"]["node_overrides"]


def test_clear_node_override_rejects_missing_port(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        profile_id = created["profile"]["profile_id"]
        result = manager.clear_node_override(profile_id, "agent.ai")

    assert result["status_code"] == 404


def test_delete_profile_reassigns_active(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        manager.create_profile({"profile_id": "p1", "base_pack": "defaultspack"})
        manager.create_profile({"profile_id": "p2", "base_pack": "defaultspack"})
        manager.activate_profile("p2")
        deleted = manager.delete_profile("p2")
        payload = manager.list_profiles_payload()

    assert deleted["deleted"] is True
    assert deleted["active_profile_id"] == "p1"
    assert payload["active_profile_id"] == "p1"
    assert len(payload["profiles"]) == 1


def test_delete_last_profile_rejected(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({"base_pack": "defaultspack"})
        result = manager.delete_profile(created["profile"]["profile_id"])

    assert result["status_code"] == 400
    assert "At least one" in result["error"]


def test_activate_profile(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        manager.create_profile({"profile_id": "my-profile", "base_pack": "defaultspack"})
        result = manager.activate_profile("my-profile")
        payload = manager.list_profiles_payload()

    assert result["activated"] is True
    assert payload["active_profile_id"] == "my-profile"


def test_duplicate_profile(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        manager.create_profile({"profile_id": "original", "base_pack": "defaultspack", "name": "Original"})
        result = manager.duplicate_profile("original")

    assert result["duplicated"] is True
    assert result["profile"]["profile_id"] != "original"
    assert "Copy" in result["profile"]["name"]
    assert result["profile"]["base_pack"] == "defaultspack"


def test_update_profile(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        manager.create_profile({"profile_id": "p1", "base_pack": "defaultspack", "name": "Original"})
        updated = manager.update_profile("p1", {"name": "Updated Name"})

    assert updated["updated"] is True
    assert updated["profile"]["name"] == "Updated Name"
    assert updated["profile"]["base_pack"] == "defaultspack"


def test_update_profile_rejects_missing_base_pack_in_packs(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    _write_pack(eco_root, "helperpack", nodes=["tool"])
    locations = _discover_locations(eco_root, ["defaultspack", "helperpack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        manager.create_profile({"profile_id": "p1", "base_pack": "defaultspack"})
        result = manager.update_profile("p1", {"packs": ["helperpack"]})

    assert result["status_code"] == 400
    assert "must be included" in result["error"]


def test_runtime_profile_v2_fields_preserved(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        created = manager.create_profile({
            "base_pack": "defaultspack",
            "name": "Rumi CLI",
            "display_name": {"ja": "Rumi CLI", "en": "Rumi CLI"},
            "locale": "ja",
            "default_flow": "cli_session",
            "default_graph": "cli_workspace",
            "capability_profile_id": "defaultspack.coding",
            "launch_capability_graph": True,
            "surfaces": {"preferred": "cli", "enabled": ["cli"]},
            "enabled_nodes": ["defaultspack.agent"],
            "disabled_nodes": ["defaultspack.frontend"],
            "node_settings": {"defaultspack.agent": {"model": "default"}},
            "policy": {"max_tool_calls": 3},
            "permissions": {"tools": "ask"},
        })

    profile = created["profile"]
    assert profile["version"] == PROFILE_VERSION
    assert profile["kind"] == "runtime_profile"
    assert profile["default_flow"] == "cli_session"
    assert profile["default_graph"] == "cli_workspace"
    assert profile["capability_profile_id"] == "defaultspack.coding"
    assert profile["launch_capability_graph"] is True
    assert profile["surfaces"] == {"preferred": "cli", "enabled": ["cli"]}
    assert profile["enabled_nodes"] == ["defaultspack.agent"]
    assert profile["disabled_nodes"] == ["defaultspack.frontend"]
    assert profile["node_settings"] == {"defaultspack.agent": {"model": "default"}}
    assert profile["policy"] == {"max_tool_calls": 3}
    assert profile["permissions"] == {"tools": "ask"}


def test_launch_profile_updates_active_ecosystem(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        identity="rumi:ecosystem/defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])
    active = _FakeActiveEcosystem()
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        with patch(
            "backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager",
            return_value=active,
        ):
            with patch("core_runtime.api.control_panel_handlers.request_kernel_restart"):
                created = manager.create_profile({"base_pack": "defaultspack", "name": "Test"})
                response = manager.launch_profile(created["profile"]["profile_id"])

    assert response["launched"] is True
    assert response["restart_requested"] is True
    assert active.active_pack_identity == "rumi:ecosystem/defaultspack"
    assert active.metadata["startup_base_pack"] == "defaultspack"
    assert active.metadata["startup_launched"] is True
    assert "rumiai.startup.base_pack" in active.interface_overrides
    assert active.overrides["ai_client"] == "defaultspack:ai_client:ai_client"
    assert active.overrides["tool"] == "defaultspack:tool:tool"
    assert "start" not in active.overrides


def test_launch_profile_with_node_override(tmp_path: Path):
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    _write_pack(eco_root, "coolpack", nodes=["ai_client"])
    locations = _discover_locations(eco_root, ["defaultspack", "coolpack"])
    active = _FakeActiveEcosystem()
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        with patch(
            "backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager",
            return_value=active,
        ):
            with patch("core_runtime.api.control_panel_handlers.request_kernel_restart"):
                created = manager.create_profile({"base_pack": "defaultspack"})
                profile_id = created["profile"]["profile_id"]
                manager.add_pack_to_profile(profile_id, "coolpack")
                manager.set_node_override(profile_id, "agent.ai", "coolpack.ai_client")
                response = manager.launch_profile(profile_id)

    assert response["launched"] is True
    assert active.metadata["startup_node_overrides"]["agent.ai"] == "coolpack.ai_client"
    assert active.overrides["ai_client"] == "coolpack:ai_client:ai_client"


def test_launch_profile_compiles_capability_graph_when_opted_in(tmp_path: Path):
    repo_defaultspack = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
    eco_root = tmp_path / "ecosystem"
    shutil.copytree(repo_defaultspack, eco_root / "defaultspack")
    interface_registry = InterfaceRegistry()
    manager = StartupProfileManager(
        storage_path=tmp_path / "startup_profiles.json",
        interface_registry=interface_registry,
        approval_manager=_FakeApprovalManager(reason_by_pack={"defaultspack": None}),
        ecosystem_dir=str(eco_root),
    )
    active = _FakeActiveEcosystem()

    with patch(
        "backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager",
        return_value=active,
    ):
        with patch("core_runtime.api.control_panel_handlers.request_kernel_restart"):
            created = manager.create_profile({
                "base_pack": "defaultspack",
                "name": "Rumi Desktop",
                "default_graph": "defaultspack.startup",
                "capability_profile_id": "defaultspack.startup",
                "launch_capability_graph": True,
            })
            response = manager.launch_profile(created["profile"]["profile_id"])

    capability_graph = response["capability_graph"]
    assert response["launched"] is True
    assert capability_graph["ok"] is True


def test_launch_profile_strict_compile_failure(tmp_path: Path):
    repo_defaultspack = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
    eco_root = tmp_path / "ecosystem"
    shutil.copytree(repo_defaultspack, eco_root / "defaultspack")
    manager = StartupProfileManager(
        storage_path=tmp_path / "startup_profiles.json",
        interface_registry=InterfaceRegistry(),
        approval_manager=_FakeApprovalManager(reason_by_pack={"defaultspack": None}),
        ecosystem_dir=str(eco_root),
    )
    active = _FakeActiveEcosystem()

    created = manager.create_profile({
        "base_pack": "defaultspack",
        "name": "Strict Runtime",
        "default_graph": "missing.graph",
        "capability_profile_id": "defaultspack.startup",
        "launch_capability_graph": True,
        "policy": {"require_capability_graph_compile": True},
    })
    before = manager.list_profiles_payload()

    with patch(
        "backend_core.ecosystem.active_ecosystem.get_active_ecosystem_manager",
        return_value=active,
    ) as mock_active:
        with patch("core_runtime.api.control_panel_handlers.request_kernel_restart") as mock_restart:
            response = manager.launch_profile(created["profile"]["profile_id"])

    after = manager.list_profiles_payload()
    assert response["status_code"] == 400
    assert response["launched"] is False
    assert after["active_profile_id"] == before["active_profile_id"]
    assert active.metadata == {}
    assert active.interface_overrides == {}
    assert active.overrides == {}
    mock_active.assert_not_called()
    mock_restart.assert_not_called()


def test_migrate_v2_slot_based_profile(tmp_path: Path):
    """Test migration from old slot-based profile to new graph-based profile."""
    eco_root = tmp_path / "ecosystem"
    _write_pack(
        eco_root, "defaultspack",
        graphs=[_startup_graph("defaultspack")],
        nodes=["agent", "ai_client", "tool", "memory", "frontend"],
    )
    locations = _discover_locations(eco_root, ["defaultspack"])

    old_state = {
        "version": 1,
        "active_profile_id": "old-profile",
        "last_launched_profile_id": None,
        "profiles": [
            {
                "profile_id": "old-profile",
                "name": "Old Profile",
                "version": 2,
                "standard_pack_id": "defaultspack",
                "slots": {
                    "tool": "defaultspack",
                    "frontend": "defaultspack",
                    "ai_client": "defaultspack",
                    "memory": "defaultspack",
                    "provider": "defaultspack",
                },
                "created_at": 1000000,
                "updated_at": 1000000,
            }
        ],
    }
    state_path = tmp_path / "startup_profiles.json"
    state_path.write_text(json.dumps(old_state), encoding="utf-8")

    manager = StartupProfileManager(storage_path=state_path)

    with patch("core_runtime.startup_profiles.discover_pack_locations", return_value=locations):
        payload = manager.list_profiles_payload()

    profile = payload["profiles"][0]
    assert profile["version"] == PROFILE_VERSION
    assert profile["base_pack"] == "defaultspack"
    assert profile["graph_id"] == "defaultspack.startup"
    assert "defaultspack" in profile["packs"]
    assert isinstance(profile["node_overrides"], dict)
    assert isinstance(profile["graph_ports"], list)
    saved_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved_state["version"] == PROFILE_VERSION
    assert saved_state["profiles"][0]["version"] == PROFILE_VERSION


def test_empty_state_returns_empty_profiles(tmp_path: Path):
    manager = StartupProfileManager(storage_path=tmp_path / "startup_profiles.json")
    payload = manager.list_profiles_payload()
    assert payload["profiles"] == []
    assert payload["active_profile_id"] is None
