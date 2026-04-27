from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from core_runtime.capability_binding_registration import register_pack_binding_handlers
from core_runtime.capability_graph_compiler import CapabilityGraphCompiler
from core_runtime.capability_graph_loader import CapabilityGraphLoader
from core_runtime.ecosystem_nodes import EcosystemNodeRegistry
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.profile_loader import CapabilityProfileLoader
from core_runtime.profile_models import load_profile_document


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ECOSYSTEM = ROOT / "tests" / "fixtures" / "ecosystem"
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
SAMPLE = FIXTURE_ECOSYSTEM / "sample_toolpack"


@dataclass
class PackInfo:
    pack_id: str
    pack_dir: Path
    pack_subdir: Path
    ecosystem_json_path: Path


class FakeApprovalManager:
    def __init__(self, approved: set[str]):
        self.approved = approved

    def is_pack_approved_and_verified(self, pack_id: str):
        return (pack_id in self.approved, None if pack_id in self.approved else "not_approved")


def _registry() -> SimpleNamespace:
    return SimpleNamespace(
        packs={
            "defaultspack": PackInfo(
                "defaultspack",
                DEFAULTSPACK,
                DEFAULTSPACK,
                DEFAULTSPACK / "ecosystem.json",
            ),
            "sample_toolpack": PackInfo(
                "sample_toolpack",
                SAMPLE,
                SAMPLE,
                SAMPLE / "ecosystem.json",
            ),
        }
    )


def test_external_pack_nodes_from_nodes_and_components_are_discovered() -> None:
    registry = EcosystemNodeRegistry(
        registry=_registry(),
        approval_manager=FakeApprovalManager({"defaultspack", "sample_toolpack"}),
    )
    nodes = registry.load_all_nodes(register=False)

    assert "sample_toolpack.search" in nodes
    assert "sample_toolpack.write_guard" in nodes


def test_external_pack_binding_registration_and_compile_to_default_agent() -> None:
    interface_registry = InterfaceRegistry()
    registry = _registry()
    approval = FakeApprovalManager({"defaultspack", "sample_toolpack"})

    registration = register_pack_binding_handlers(
        interface_registry=interface_registry,
        registry=registry,
        approval_manager=approval,
    )
    assert registration.ok is True
    assert set(registration.registered) == {"defaultspack", "sample_toolpack"}

    node_registry = EcosystemNodeRegistry(registry=registry, approval_manager=approval)
    graph_loader = CapabilityGraphLoader(
        registry=registry,
        approval_manager=approval,
        shared_graphs_dir=ROOT / "missing-user-graphs",
        workspace_graphs_dir=ROOT / "missing-workspace-graphs",
    )
    profile_loader = CapabilityProfileLoader(registry=registry, approval_manager=approval)

    graph = graph_loader.get_graph("sample_toolpack_to_default_agent")
    profile = profile_loader.get_profile("sample_toolpack.profile")
    assert graph is not None
    assert profile is not None

    result = CapabilityGraphCompiler(interface_registry=interface_registry).compile(
        graph,
        profile=profile,
        nodes=node_registry.load_all_nodes(register=False),
        register=True,
    )

    assert result.ok is True
    runtime_profile = result.runtime_profile or {}
    agent = runtime_profile["defaultspack"]["agents"]["agent"]
    assert "sample_search" in runtime_profile["defaultspack"]["tools"]["sample_search"]["tools"]
    assert "sample_search" in agent["tools"]
    assert interface_registry.get(runtime_profile["registry_key"]) is runtime_profile


def test_external_node_disabled_by_profile_is_rejected() -> None:
    interface_registry = InterfaceRegistry()
    registry = _registry()
    approval = FakeApprovalManager({"defaultspack", "sample_toolpack"})
    register_pack_binding_handlers(
        interface_registry=interface_registry,
        registry=registry,
        approval_manager=approval,
    )
    node_registry = EcosystemNodeRegistry(registry=registry, approval_manager=approval)
    graph = CapabilityGraphLoader(
        registry=registry,
        approval_manager=approval,
        shared_graphs_dir=ROOT / "missing-user-graphs",
        workspace_graphs_dir=ROOT / "missing-workspace-graphs",
    ).get_graph("sample_toolpack_to_default_agent")
    assert graph is not None
    disabled_profile = load_profile_document(
        {
            "version": "rumi.profile.v1",
            "profile_id": "sample.disabled",
            "enabled_nodes": ["rumi.start", "defaultspack.agent", "defaultspack.ai_client"],
            "disabled_nodes": ["sample_toolpack.search"],
        }
    )

    result = CapabilityGraphCompiler(interface_registry=interface_registry).compile(
        graph,
        profile=disabled_profile,
        nodes=node_registry.load_all_nodes(register=False),
    )

    assert result.ok is False
    assert any(item["code"] == "profile_node_unavailable" for item in result.diagnostics)


def test_unapproved_pack_binding_registration_is_skipped() -> None:
    result = register_pack_binding_handlers(
        interface_registry=InterfaceRegistry(),
        registry=_registry(),
        approval_manager=FakeApprovalManager({"defaultspack"}),
    )

    assert "defaultspack" in result.registered
    assert "sample_toolpack" in result.skipped
    assert any(item["code"] == "binding_registration_pack_skipped_unapproved" for item in result.diagnostics)
