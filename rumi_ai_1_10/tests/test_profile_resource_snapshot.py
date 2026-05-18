from __future__ import annotations

import json
from pathlib import Path

import yaml

from core_runtime.profile_workspace import ProfileWorkspaceManager
from core_runtime.profile_resource_snapshot import ProfileResourceSnapshotManager


def _write_pack(root: Path) -> None:
    pack = root / "defaultspack"
    (pack / "flows").mkdir(parents=True)
    (pack / "graphs").mkdir()
    (pack / "flows" / "chat_turn.flow.yaml").write_text("flow_id: defaultspack.chat_turn\nsteps: []\n", encoding="utf-8")
    (pack / "graphs" / "startup.graph.yaml").write_text(
        yaml.safe_dump({"graph_id": "defaultspack.startup", "nodes": [{"id": "agent", "ref": "defaultspack.agent", "block": "blocks.agent"}]}),
        encoding="utf-8",
    )
    (pack / "ecosystem.json").write_text(json.dumps({"pack_id": "defaultspack", "enabled": True}), encoding="utf-8")


def test_defaultspack_snapshot_writes_manifest_lock(tmp_path: Path):
    ecosystem_root = tmp_path / "ecosystem"
    _write_pack(ecosystem_root)
    ProfileWorkspaceManager(tmp_path / "user_data").initialize_profile_workspace({"profile_id": "default-profile"})

    manifest = ProfileResourceSnapshotManager(
        tmp_path / "user_data",
        ecosystem_dir=str(ecosystem_root),
    ).snapshot_default_resources(
        "default-profile",
        base_pack="defaultspack",
        graph_id="defaultspack.startup",
        flow_ids=["chat_turn"],
    )

    manifest_path = tmp_path / "user_data" / "profiles" / "default-profile" / "ecosystem" / "snapshots" / "defaultspack" / "manifest.lock.json"
    assert manifest_path.is_file()
    assert manifest["items"][0]["type"] == "flow"


def test_snapshot_records_source_hashes(tmp_path: Path):
    ecosystem_root = tmp_path / "ecosystem"
    _write_pack(ecosystem_root)

    manifest = ProfileResourceSnapshotManager(
        tmp_path / "user_data",
        ecosystem_dir=str(ecosystem_root),
    ).snapshot_default_resources("p1", base_pack="defaultspack", flow_ids=["chat_turn"])

    assert len(manifest["items"][0]["sha256"]) == 64
    assert manifest["items"][0]["source"] == "flows/chat_turn.flow.yaml"
