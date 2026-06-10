from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import core_runtime.capability_graph_compiler as compiler_module
from core_runtime.binding_handlers import BindingHandlerResolver
from core_runtime.capability_graph_compiler import CapabilityGraphCompiler
from core_runtime.capability_graph_loader import CapabilityGraphLoader, GraphDiscoveryError
from core_runtime.ecosystem_nodes import EcosystemNodeRegistry
from core_runtime.flow_loader import FlowLoader
from core_runtime.kernel import Kernel
from core_runtime.kernel_flow_converter import FlowConverter
from core_runtime.graph_models import GraphValidationError, load_graph_document
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.profile_loader import CapabilityProfileLoader
from core_runtime.profile_models import load_profile_document


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
        if rel_path.endswith(".json"):
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return SimpleNamespace(pack_id=pack_id, subdir=pack_dir, path=pack_dir)


def _registry(*packs: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(packs={pack.pack_id: pack for pack in packs})


def _node_doc(*nodes: dict) -> dict:
    return {"version": "rumi.node.v1", "nodes": list(nodes)}


def _graph_doc(graph_id: str = "samplepack.coding", **overrides) -> dict:
    data = {
        "graph_id": graph_id,
        "version": "rumi.graph.v1",
        "display_name": {"en": graph_id},
        "nodes": [
            {"id": "start", "ref": "rumi.start"},
            {"id": "source", "ref": "samplepack.source"},
            {"id": "target", "ref": "samplepack.target"},
        ],
        "edges": [
            {"id": "start_to_target", "from": "start.out", "to": "target.start", "kind": "binding"},
            {"id": "source_to_target", "from": "source.out", "to": "target.in", "kind": "binding"},
        ],
    }
    data.update(overrides)
    return data


def _profile_doc(profile_id: str = "coding", **overrides) -> dict:
    data = {
        "profile_id": profile_id,
        "version": "rumi.profile.v1",
        "enabled_nodes": ["rumi.start", "samplepack.source", "samplepack.target"],
        "disabled_nodes": [],
    }
    data.update(overrides)
    return data


def _sample_node_pack(tmp_path, *, target_multiple: bool = False) -> SimpleNamespace:
    return _pack(
        tmp_path,
        "samplepack",
        {
            "components/source/node.json": _node_doc(
                {
                    "node_id": "samplepack.source",
                    "ports": [
                        {
                            "id": "out",
                            "direction": "output",
                            "standards": ["sample.standard"],
                        }
                    ],
                }
            ),
            "components/target/node.json": _node_doc(
                {
                    "node_id": "samplepack.target",
                    "ports": [
                        {
                            "id": "start",
                            "direction": "input",
                            "standards": ["rumi.flow.start"],
                            "required": True,
                        },
                        {
                            "id": "in",
                            "direction": "input",
                            "standards": ["sample.standard"],
                            "multiple": target_multiple,
                            "required": True,
                        },
                    ],
                }
            ),
        },
    )


def test_graph_fields_are_normalized() -> None:
    graph = load_graph_document(
        _graph_doc(
            "coding",
            name="Coding",
            display_name={},
            nodes=[{"id": "agent", "ref": "samplepack.target"}],
            edges=[],
        )
    )

    assert graph.display_name["en"] == "Coding"
    assert graph.nodes[0].id == "agent"


def test_invalid_graph_version_is_rejected() -> None:
    with pytest.raises(GraphValidationError, match="unsupported graph version"):
        load_graph_document({"graph_id": "bad", "version": "rumi.graph.v0", "nodes": []})


def test_pack_graphs_load_only_from_approved_packs(tmp_path) -> None:
    approved = _pack(
        tmp_path,
        "approvedpack",
        {"graphs/coding.graph.yaml": _graph_doc("approvedpack.coding", nodes=[{"id": "n", "ref": "approvedpack.node"}], edges=[])},
    )
    unapproved = _pack(
        tmp_path,
        "unapprovedpack",
        {"graphs/guest.graph.yaml": _graph_doc("unapprovedpack.guest", nodes=[{"id": "n", "ref": "unapprovedpack.node"}], edges=[])},
    )
    interface_registry = InterfaceRegistry()
    loader = CapabilityGraphLoader(
        registry=_registry(approved, unapproved),
        approval_manager=FakeApprovalManager({"approvedpack"}),
        interface_registry=interface_registry,
        shared_graphs_dir=tmp_path / "missing-user-graphs",
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )

    graphs = loader.load_all_graphs()

    assert set(graphs) == {"approvedpack.coding"}
    assert loader.diagnostics[0]["code"] == "pack_skipped_unapproved"
    assert interface_registry.get("graph.approvedpack.coding").graph_id == "approvedpack.coding"


def test_user_shared_graphs_are_schema_validated(tmp_path) -> None:
    shared_dir = tmp_path / "user_data" / "shared" / "graphs"
    shared_dir.mkdir(parents=True)
    (shared_dir / "broken.graph.yaml").write_text(
        yaml.safe_dump({"graph_id": "broken", "version": "wrong"}),
        encoding="utf-8",
    )
    loader = CapabilityGraphLoader(
        registry=_registry(),
        approval_manager=FakeApprovalManager(),
        shared_graphs_dir=shared_dir,
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )

    with pytest.raises(GraphDiscoveryError):
        loader.load_all_graphs()

    assert loader.diagnostics[0]["code"] == "invalid_graph_file"


def test_duplicate_graph_ids_are_rejected(tmp_path) -> None:
    shared_dir = tmp_path / "graphs"
    shared_dir.mkdir()
    (shared_dir / "a.graph.yaml").write_text(
        yaml.safe_dump(_graph_doc("coding", nodes=[{"id": "a", "ref": "samplepack.a"}], edges=[])),
        encoding="utf-8",
    )
    (shared_dir / "b.graph.yaml").write_text(
        yaml.safe_dump(_graph_doc("coding", nodes=[{"id": "b", "ref": "samplepack.b"}], edges=[])),
        encoding="utf-8",
    )
    loader = CapabilityGraphLoader(
        registry=_registry(),
        approval_manager=FakeApprovalManager(),
        shared_graphs_dir=shared_dir,
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )

    with pytest.raises(GraphDiscoveryError, match="duplicate graph_id 'coding'"):
        loader.load_all_graphs()


def test_graph_validation_accepts_matching_ports_and_profile(tmp_path) -> None:
    pack = _sample_node_pack(tmp_path)
    graph_pack = _pack(
        tmp_path,
        "graphpack",
        {"graphs/coding.graph.yaml": _graph_doc("graphpack.coding")},
    )
    registry = _registry(pack, graph_pack)
    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
    )
    loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
        shared_graphs_dir=tmp_path / "missing-user-graphs",
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )
    profile = load_profile_document(_profile_doc())

    result = loader.validate_graph(
        "graphpack.coding",
        node_registry=node_registry,
        profile=profile,
    )

    assert result.ok is True
    assert result.diagnostics == []


def test_graph_validation_reports_node_profile_port_and_standard_errors(tmp_path) -> None:
    pack = _sample_node_pack(tmp_path)
    graph_pack = _pack(
        tmp_path,
        "graphpack",
        {
            "graphs/coding.graph.yaml": _graph_doc(
                "graphpack.coding",
                nodes=[
                    {"id": "start", "ref": "rumi.start"},
                    {"id": "source", "ref": "samplepack.source"},
                    {"id": "target", "ref": "samplepack.target"},
                    {"id": "missing", "ref": "samplepack.missing"},
                ],
                edges=[
                    {"id": "bad_direction", "from": "target.in", "to": "source.out", "kind": "binding"},
                    {"id": "missing_port", "from": "source.missing", "to": "target.in", "kind": "binding"},
                    {"id": "mismatch", "from": "start.out", "to": "target.in", "kind": "binding"},
                ],
            )
        },
    )
    registry = _registry(pack, graph_pack)
    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
    )
    loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
        shared_graphs_dir=tmp_path / "missing-user-graphs",
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )
    profile = load_profile_document(_profile_doc(disabled_nodes=["samplepack.source"]))

    result = loader.validate_graph(
        "graphpack.coding",
        node_registry=node_registry,
        profile=profile,
    )

    codes = {item["code"] for item in result.diagnostics}
    assert result.ok is False
    assert "missing_node_ref" in codes
    assert "profile_node_unavailable" in codes
    assert "invalid_source_direction" in codes
    assert "invalid_target_direction" in codes
    assert "missing_port" in codes
    assert "standards_mismatch" in codes


def test_graph_validation_enforces_multiple_false_and_required_inputs(tmp_path) -> None:
    pack = _sample_node_pack(tmp_path, target_multiple=False)
    graph_pack = _pack(
        tmp_path,
        "graphpack",
        {
            "graphs/coding.graph.yaml": _graph_doc(
                "graphpack.coding",
                edges=[
                    {"id": "first", "from": "source.out", "to": "target.in", "kind": "binding"},
                    {"id": "second", "from": "source.out", "to": "target.in", "kind": "binding"},
                ],
            )
        },
    )
    registry = _registry(pack, graph_pack)
    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
    )
    loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
        shared_graphs_dir=tmp_path / "missing-user-graphs",
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )

    result = loader.validate_graph(
        "graphpack.coding",
        node_registry=node_registry,
        profile=load_profile_document(_profile_doc()),
    )

    codes = {item["code"] for item in result.diagnostics}
    assert result.ok is False
    assert "input_multiple_violation" in codes
    assert "required_input_missing" in codes


def test_graph_compiler_validates_before_compile_and_returns_diagnostics(tmp_path) -> None:
    pack = _sample_node_pack(tmp_path)
    graph_pack = _pack(
        tmp_path,
        "graphpack",
        {
            "graphs/coding.graph.yaml": _graph_doc(
                "graphpack.coding",
                edges=[
                    {"id": "bad", "from": "start.out", "to": "target.in", "kind": "binding"},
                ],
            )
        },
    )
    registry = _registry(pack, graph_pack)
    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
    )
    loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
        shared_graphs_dir=tmp_path / "missing-user-graphs",
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )
    graph = loader.get_graph("graphpack.coding")
    assert graph is not None

    result = CapabilityGraphCompiler().compile(
        graph,
        profile=load_profile_document(_profile_doc()),
        nodes=node_registry.load_all_nodes(register=False),
    )

    assert result.ok is False
    assert result.runtime_profile is None
    assert {item["code"] for item in result.diagnostics} >= {
        "standards_mismatch",
        "required_input_missing",
    }


def test_graph_compiler_builds_profile_runs_handlers_and_registers_runtime_profile(tmp_path) -> None:
    pack = _pack(
        tmp_path,
        "samplepack",
        {
            "components/source/node.json": _node_doc(
                {
                    "node_id": "samplepack.source",
                    "ports": [
                        {
                            "id": "out",
                            "direction": "output",
                            "standards": ["sample.standard"],
                        }
                    ],
                }
            ),
            "components/target/node.json": _node_doc(
                {
                    "node_id": "samplepack.target",
                    "ports": [
                        {
                            "id": "start",
                            "direction": "input",
                            "standards": ["rumi.flow.start"],
                            "required": True,
                        },
                        {
                            "id": "in",
                            "direction": "input",
                            "standards": ["sample.standard"],
                            "required": True,
                        },
                    ],
                    "bindings": {
                        "compile": "binding:target.compile",
                        "on_input": {"in": "binding:target.input"},
                    },
                }
            ),
        },
    )
    graph_pack = _pack(
        tmp_path,
        "graphpack",
        {"graphs/coding.graph.yaml": _graph_doc("graphpack.coding")},
    )
    registry = _registry(pack, graph_pack)
    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
    )
    loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
        shared_graphs_dir=tmp_path / "missing-user-graphs",
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )
    interface_registry = InterfaceRegistry()
    calls = []

    def compile_handler(**kwargs):
        calls.append(("compile", kwargs["instance"].id))
        kwargs["runtime_profile"].setdefault("handler_notes", []).append("compile")

    def input_handler(**kwargs):
        calls.append(("input", kwargs["edge"].id))
        kwargs["runtime_profile"].setdefault("handler_notes", []).append("input")

    interface_registry.register("binding:target.compile", compile_handler)
    interface_registry.register("binding:target.input", input_handler)
    graph = loader.get_graph("graphpack.coding")
    assert graph is not None

    result = CapabilityGraphCompiler(interface_registry=interface_registry).compile(
        graph,
        profile=load_profile_document(
            _profile_doc(
                node_settings={"samplepack.target": {"setting": "value"}},
            )
        ),
        nodes=node_registry.load_all_nodes(register=False),
    )

    assert result.ok is True
    assert result.runtime_profile is not None
    assert result.runtime_profile["version"] == "rumi.runtime_profile.v1"
    assert result.runtime_profile["nodes"]["target"]["settings"] == {"setting": "value"}
    assert result.runtime_profile["handler_notes"] == ["compile", "input"]
    assert calls == [("compile", "target"), ("input", "source_to_target")]
    assert result.runtime_profile["registry_key"] == "runtime_profile.coding.graphpack.coding"
    assert interface_registry.get("runtime_profile.coding.graphpack.coding") is result.runtime_profile


def test_binding_handler_resolver_rejects_import_paths() -> None:
    resolver = BindingHandlerResolver(interface_registry=InterfaceRegistry())

    result = resolver.resolve("some.module.handler")

    assert result.handler is None
    assert result.diagnostics[0]["code"] == "binding_handler_import_path_rejected"


def test_graph_compiler_reports_missing_binding_handler(tmp_path) -> None:
    pack = _pack(
        tmp_path,
        "samplepack",
        {
            "components/source/node.json": _node_doc(
                {
                    "node_id": "samplepack.source",
                    "ports": [{"id": "out", "direction": "output", "standards": ["sample.standard"]}],
                }
            ),
            "components/target/node.json": _node_doc(
                {
                    "node_id": "samplepack.target",
                    "ports": [
                        {"id": "start", "direction": "input", "standards": ["rumi.flow.start"], "required": True},
                        {"id": "in", "direction": "input", "standards": ["sample.standard"], "required": True},
                    ],
                    "bindings": {"on_input": {"in": "binding:missing"}},
                }
            ),
        },
    )
    graph_pack = _pack(
        tmp_path,
        "graphpack",
        {"graphs/coding.graph.yaml": _graph_doc("graphpack.coding")},
    )
    registry = _registry(pack, graph_pack)
    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
    )
    loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
        shared_graphs_dir=tmp_path / "missing-user-graphs",
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )
    graph = loader.get_graph("graphpack.coding")
    assert graph is not None

    result = CapabilityGraphCompiler(interface_registry=InterfaceRegistry()).compile(
        graph,
        profile=load_profile_document(_profile_doc()),
        nodes=node_registry.load_all_nodes(register=False),
    )

    assert result.ok is False
    assert result.runtime_profile is None
    assert result.diagnostics[-1]["code"] == "binding_handler_not_found"


def test_graph_compiler_does_not_retry_handler_internal_type_error(tmp_path) -> None:
    pack = _pack(
        tmp_path,
        "samplepack",
        {
            "components/source/node.json": _node_doc(
                {
                    "node_id": "samplepack.source",
                    "ports": [{"id": "out", "direction": "output", "standards": ["sample.standard"]}],
                }
            ),
            "components/target/node.json": _node_doc(
                {
                    "node_id": "samplepack.target",
                    "ports": [
                        {"id": "start", "direction": "input", "standards": ["rumi.flow.start"], "required": True},
                        {"id": "in", "direction": "input", "standards": ["sample.standard"], "required": True},
                    ],
                    "bindings": {"on_input": {"in": "binding:buggy"}},
                }
            ),
        },
    )
    graph_pack = _pack(
        tmp_path,
        "graphpack",
        {"graphs/coding.graph.yaml": _graph_doc("graphpack.coding")},
    )
    registry = _registry(pack, graph_pack)
    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
    )
    loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=FakeApprovalManager({"samplepack", "graphpack"}),
        shared_graphs_dir=tmp_path / "missing-user-graphs",
        workspace_graphs_dir=tmp_path / "missing-workspace-graphs",
    )
    interface_registry = InterfaceRegistry()
    calls = []

    def buggy_handler(**kwargs):
        calls.append(kwargs["edge"].id)
        raise TypeError("internal handler bug")

    interface_registry.register("binding:buggy", buggy_handler)
    graph = loader.get_graph("graphpack.coding")
    assert graph is not None

    result = CapabilityGraphCompiler(interface_registry=interface_registry).compile(
        graph,
        profile=load_profile_document(_profile_doc()),
        nodes=node_registry.load_all_nodes(register=False),
    )

    assert calls == ["source_to_target"]
    assert result.ok is False
    assert result.runtime_profile is None
    assert result.diagnostics[-1]["code"] == "binding_handler_failed"
    assert "internal handler bug" in result.diagnostics[-1]["message"]


def test_graph_compiler_core_has_no_domain_specific_branches() -> None:
    source = inspect.getsource(compiler_module)

    for forbidden in ('"ai"', '"tool"', '"agent"', "== 'ai'", "== 'tool'", "== 'agent'"):
        assert forbidden not in source


def test_defaultspack_minimal_bindings_compile_sample_graph() -> None:
    from ecosystem.defaultspack.capability_bindings import (
        register_defaultspack_binding_handlers,
    )

    defaultspack_root = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
    pack = SimpleNamespace(
        pack_id="defaultspack",
        subdir=defaultspack_root,
        path=defaultspack_root,
    )
    registry = _registry(pack)
    approval_manager = FakeApprovalManager({"defaultspack", "rumi_local_agent_pack"})
    interface_registry = InterfaceRegistry()
    register_defaultspack_binding_handlers(interface_registry)

    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=approval_manager,
        interface_registry=interface_registry,
    )
    graph_loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=approval_manager,
        interface_registry=interface_registry,
        shared_graphs_dir=defaultspack_root / "missing-user-graphs",
        workspace_graphs_dir=defaultspack_root / "missing-workspace-graphs",
    )
    profile_loader = CapabilityProfileLoader(
        registry=registry,
        approval_manager=approval_manager,
        interface_registry=interface_registry,
        shared_profiles_dir=defaultspack_root / "missing-user-profiles",
    )
    graph = graph_loader.get_graph("defaultspack.coding_workspace")
    profile = profile_loader.get_profile("defaultspack.coding")
    assert graph is not None
    assert profile is not None

    result = CapabilityGraphCompiler(interface_registry=interface_registry).compile(
        graph,
        profile=profile,
        nodes=node_registry.load_all_nodes(register=True),
    )

    assert result.ok is True
    assert result.runtime_profile is not None
    defaultspack = result.runtime_profile["defaultspack"]
    assert defaultspack["agents"]["agent"]["ai"] == "ai"
    assert defaultspack["agents"]["agent"]["tools"] == ["tools"]
    assert defaultspack["frontends"]["frontend"]["surface"] == "cli"
    assert defaultspack["frontends"]["frontend"]["surfaces"] == ["cli"]
    assert set(defaultspack["ai_clients"]) == {"ai"}
    assert set(defaultspack["tools"]) == {"tools"}
    assert set(defaultspack["cli_surfaces"]) == {"cli"}


def test_defaultspack_startup_graph_compiles_with_memory_and_prompt_nodes() -> None:
    from ecosystem.defaultspack.capability_bindings import (
        register_defaultspack_binding_handlers,
    )

    defaultspack_root = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
    pack = SimpleNamespace(
        pack_id="defaultspack",
        subdir=defaultspack_root,
        path=defaultspack_root,
    )
    registry = _registry(pack)
    approval_manager = FakeApprovalManager({"defaultspack", "rumi_local_agent_pack"})
    interface_registry = InterfaceRegistry()
    register_defaultspack_binding_handlers(interface_registry)

    node_registry = EcosystemNodeRegistry(
        registry=registry,
        approval_manager=approval_manager,
        interface_registry=interface_registry,
    )
    graph_loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=approval_manager,
        interface_registry=interface_registry,
        shared_graphs_dir=defaultspack_root / "missing-user-graphs",
        workspace_graphs_dir=defaultspack_root / "missing-workspace-graphs",
    )
    profile_loader = CapabilityProfileLoader(
        registry=registry,
        approval_manager=approval_manager,
        interface_registry=interface_registry,
        shared_profiles_dir=defaultspack_root / "missing-user-profiles",
    )
    graph = graph_loader.get_graph("defaultspack.startup")
    profile = profile_loader.get_profile("defaultspack.startup")
    assert graph is not None
    assert profile is not None

    nodes = node_registry.load_all_nodes(register=True)
    assert "defaultspack.memory" in nodes
    assert "defaultspack.prompt" in nodes

    result = CapabilityGraphCompiler(interface_registry=interface_registry).compile(
        graph,
        profile=profile,
        nodes=nodes,
    )

    assert result.ok is True
    assert result.runtime_profile is not None
    agent = result.runtime_profile["defaultspack"]["agents"]["agent"]
    assert agent["memory"] == "memory"
    assert agent["prompt"] == "prompt"
    assert set(result.runtime_profile["defaultspack"]["memory"]) == {"memory"}
    assert set(result.runtime_profile["defaultspack"]["prompts"]) == {"prompt"}


def test_defaultspack_startup_graph_override_writes_frontend_launch_target(tmp_path, monkeypatch) -> None:
    from core_runtime.startup_capability_bridge import compile_startup_capabilities

    monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
    repo_root = Path(__file__).resolve().parents[1]
    ecosystem_root = tmp_path / "ecosystem"
    shutil.copytree(repo_root / "ecosystem" / "defaultspack", ecosystem_root / "defaultspack")
    copied_manifest_path = ecosystem_root / "defaultspack" / "ecosystem.json"
    copied_manifest = json.loads(copied_manifest_path.read_text(encoding="utf-8"))
    copied_manifest["host_execution"] = True
    copied_manifest_path.write_text(json.dumps(copied_manifest), encoding="utf-8")
    frontendpack = ecosystem_root / "frontendpack"
    frontendpack.mkdir(parents=True)
    (frontendpack / "ecosystem.json").write_text(
        json.dumps(
            {
                "pack_id": "frontendpack",
                "pack_identity": "test:frontendpack",
                "version": "1.0.0",
                "enabled": True,
                "desktop_app": {
                    "module": "frontendpack.desktop_app",
                    "handler": "launch",
                },
            }
        ),
        encoding="utf-8",
    )
    component_dir = frontendpack / "components" / "web"
    component_dir.mkdir(parents=True)
    (component_dir / "node.json").write_text(
        json.dumps(
            _node_doc(
                {
                    "node_id": "frontendpack.web_surface",
                    "kind": "ecosystem.surface",
                    "ports": [
                        {
                            "id": "surface",
                            "direction": "output",
                            "standards": ["rumi.surface"],
                            "multiple": True,
                        }
                    ],
                    "metadata": {
                        "pack_id": "frontendpack",
                        "component_type": "frontend",
                        "component_id": "web",
                        "category": "surface",
                        "launch": {
                            "kind": "desktop_app",
                            "pack_id": "frontendpack",
                            "surface": "browser",
                            "default": True,
                            "env": {"FRONTENDPACK_SURFACE": "web"},
                        },
                    },
                }
            )
        ),
        encoding="utf-8",
    )

    result = compile_startup_capabilities(
        {
            "base_pack": "defaultspack",
            "default_graph": "defaultspack.startup",
            "capability_profile_id": "defaultspack.startup",
            "packs": ["defaultspack", "frontendpack"],
            "node_overrides": {"frontend.surface": "frontendpack.web_surface"},
            "surfaces": {"preferred": "browser", "enabled": ["browser"]},
        },
        interface_registry=InterfaceRegistry(),
        approval_manager=FakeApprovalManager({"defaultspack", "frontendpack", "rumi_local_agent_pack"}),
        ecosystem_dir=str(ecosystem_root),
    )

    assert result.ok is True
    runtime_profile = result.runtime_profile or {}
    assert runtime_profile["defaultspack"]["frontends"]["frontend"]["surface"] == "frontendpack_web_surface"
    assert runtime_profile["launch"]["surface"]["pack_id"] == "frontendpack"
    assert runtime_profile["launch"]["surface"]["node_id"] == "frontendpack.web_surface"
    assert result.surface_launch_target is not None
    assert result.surface_launch_target["pack_id"] == "frontendpack"


def test_flow_step_can_explicitly_compile_defaultspack_graph() -> None:
    from ecosystem.defaultspack.capability_bindings import (
        register_defaultspack_binding_handlers,
    )

    repo_root = Path(__file__).resolve().parents[1]
    defaultspack_root = repo_root / "ecosystem" / "defaultspack"
    flow_path = defaultspack_root / "flows" / "coding_workspace_compile.flow.yaml"
    pack = SimpleNamespace(
        pack_id="defaultspack",
        subdir=defaultspack_root,
        path=defaultspack_root,
    )
    registry = _registry(pack)
    approval_manager = FakeApprovalManager({"defaultspack", "rumi_local_agent_pack"})
    interface_registry = InterfaceRegistry()
    register_defaultspack_binding_handlers(interface_registry)

    loaded = FlowLoader().load_flow_file(
        flow_path,
        source_type="pack",
        pack_id="defaultspack",
    )
    assert loaded.success is True
    assert loaded.flow_def is not None
    flow_def = FlowConverter().convert_flow_def_to_legacy(loaded.flow_def)

    kernel = Kernel(interface_registry=interface_registry)
    kernel.interface_registry.register(f"flow.{loaded.flow_id}", flow_def)
    try:
        result = kernel.execute_flow_sync(
            str(loaded.flow_id),
            {
                "registry": registry,
                "approval_manager": approval_manager,
            },
        )
    finally:
        kernel._executor.shutdown(wait=True)

    compiled = result["compiled_runtime_profile"]
    assert compiled["_kernel_step_status"] == "success"
    assert compiled["ok"] is True
    runtime_profile = compiled["runtime_profile"]
    assert runtime_profile["registry_key"] == (
        "runtime_profile.defaultspack.coding.defaultspack.coding_workspace"
    )
    assert runtime_profile["defaultspack"]["agents"]["agent"]["ai"] == "ai"
    assert runtime_profile["defaultspack"]["agents"]["agent"]["tools"] == ["tools"]
    assert kernel.interface_registry.get(runtime_profile["registry_key"]) == runtime_profile
