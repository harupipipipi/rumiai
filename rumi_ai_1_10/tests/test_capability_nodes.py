from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core_runtime.ecosystem_nodes import EcosystemNodeRegistry, NodeDiscoveryError
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.node_models import (
    CORE_START_NODE_ID,
    CORE_START_STANDARD,
    NodeDefinition,
    NodeValidationError,
    load_node_document,
)


class FakeApprovalManager:
    def __init__(self, approved: set[str] | None = None) -> None:
        self.approved = approved or set()

    def is_pack_approved_and_verified(self, pack_id: str):
        if pack_id in self.approved:
            return True, None
        return False, "not_approved"


def _pack(tmp_path, pack_id: str, files: dict[str, dict]) -> SimpleNamespace:
    pack_dir = tmp_path / pack_id
    pack_dir.mkdir()
    (pack_dir / "ecosystem.json").write_text(
        json.dumps(
            {
                "pack_id": pack_id,
                "pack_identity": f"test:{pack_id}",
                "version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )
    for rel_path, payload in files.items():
        path = pack_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    return SimpleNamespace(pack_id=pack_id, subdir=pack_dir, path=pack_dir)


def _registry(*packs: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(packs={pack.pack_id: pack for pack in packs})


def _node_doc(*nodes: dict) -> dict:
    return {"version": "rumi.node.v1", "nodes": list(nodes)}


def test_legacy_name_and_contract_are_normalized() -> None:
    [node] = load_node_document(
        _node_doc(
            {
                "node_id": "pack.agent",
                "name": "Agent",
                "ports": [
                    {
                        "id": "tools",
                        "direction": "input",
                        "contract": "rumi.tool.bundle",
                    }
                ],
            }
        )
    )

    assert node.display_name["en"] == "Agent"
    assert node.ports[0].standards == ["rumi.tool.bundle"]
    assert node.display_label("ja") == "Agent"


def test_invalid_direction_is_rejected() -> None:
    with pytest.raises(NodeValidationError, match="invalid direction"):
        load_node_document(
            _node_doc(
                {
                    "node_id": "pack.bad",
                    "ports": [
                        {
                            "id": "out",
                            "direction": "sideways",
                            "standards": ["rumi.tool.bundle"],
                        }
                    ],
                }
            )
        )


def test_invalid_standards_are_rejected() -> None:
    with pytest.raises(NodeValidationError, match="invalid standard"):
        load_node_document(
            _node_doc(
                {
                    "node_id": "pack.bad",
                    "ports": [
                        {
                            "id": "out",
                            "direction": "output",
                            "standards": ["not a standard"],
                        }
                    ],
                }
            )
        )


def test_multiple_nodes_from_one_file_are_loaded_and_registered(tmp_path) -> None:
    pack = _pack(
        tmp_path,
        "samplepack",
        {
            "nodes/runtime.node.json": _node_doc(
                {
                    "node_id": "samplepack.first",
                    "display_name": {"en": "First"},
                    "ports": [
                        {
                            "id": "out",
                            "direction": "output",
                            "standards": ["samplepack.first.v1"],
                        }
                    ],
                },
                {
                    "node_id": "samplepack.second",
                    "display_name": {"en": "Second"},
                    "ports": [
                        {
                            "id": "in",
                            "direction": "input",
                            "standards": ["samplepack.first.v1"],
                        }
                    ],
                },
            )
        },
    )
    interface_registry = InterfaceRegistry()
    node_registry = EcosystemNodeRegistry(
        registry=_registry(pack),
        approval_manager=FakeApprovalManager({"samplepack"}),
        interface_registry=interface_registry,
    )

    nodes = node_registry.load_all_nodes()

    assert list(nodes)[0] == CORE_START_NODE_ID
    assert set(nodes) == {CORE_START_NODE_ID, "samplepack.first", "samplepack.second"}
    assert isinstance(interface_registry.get("node.samplepack.first"), NodeDefinition)
    start = interface_registry.get("node.rumi.start")
    assert start.get_port("out").standards == [CORE_START_STANDARD]


def test_component_node_json_is_discovered(tmp_path) -> None:
    pack = _pack(
        tmp_path,
        "componentpack",
        {
            "components/agent/node.json": _node_doc(
                {
                    "node_id": "componentpack.agent",
                    "ports": [
                        {
                            "id": "start",
                            "direction": "input",
                            "standards": ["rumi.flow.start"],
                        }
                    ],
                }
            )
        },
    )
    node_registry = EcosystemNodeRegistry(
        registry=_registry(pack),
        approval_manager=FakeApprovalManager({"componentpack"}),
    )

    nodes = node_registry.load_all_nodes(register=False)

    assert "componentpack.agent" in nodes


def test_duplicate_node_id_is_rejected(tmp_path) -> None:
    pack = _pack(
        tmp_path,
        "dupepack",
        {
            "nodes/a.node.json": _node_doc({"node_id": "dupepack.node", "ports": []}),
            "nodes/b.node.json": _node_doc({"node_id": "dupepack.node", "ports": []}),
        },
    )
    node_registry = EcosystemNodeRegistry(
        registry=_registry(pack),
        approval_manager=FakeApprovalManager({"dupepack"}),
    )

    with pytest.raises(NodeDiscoveryError, match="duplicate node_id"):
        node_registry.load_all_nodes(register=False)


def test_unapproved_pack_node_files_are_skipped(tmp_path) -> None:
    pack = _pack(
        tmp_path,
        "unapproved",
        {
            "nodes/tool.node.json": _node_doc(
                {
                    "node_id": "unapproved.tool",
                    "ports": [
                        {
                            "id": "tools",
                            "direction": "output",
                            "standards": ["rumi.tool.bundle"],
                        }
                    ],
                }
            )
        },
    )
    node_registry = EcosystemNodeRegistry(
        registry=_registry(pack),
        approval_manager=FakeApprovalManager(set()),
    )

    nodes = node_registry.load_all_nodes(register=False)

    assert set(nodes) == {CORE_START_NODE_ID}
    assert node_registry.diagnostics[0]["code"] == "pack_skipped_unapproved"
