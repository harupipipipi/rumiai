from __future__ import annotations

from core_runtime.graph_models import load_graph_document
from core_runtime.node_models import load_node_document
from core_runtime.profile_models import CapabilityProfileDefinition
from core_runtime.startup_capability_bridge import extend_profile_for_startup_overrides
from core_runtime.startup_graph_overrides import apply_startup_node_overrides


def _nodes(*node_payloads: dict):
    definitions = load_node_document({"version": "rumi.node.v1", "nodes": list(node_payloads)})
    return {node.node_id: node for node in definitions}


def _startup_graph():
    return load_graph_document(
        {
            "version": "rumi.graph.v1",
            "graph_id": "defaultspack.startup",
            "nodes": [
                {"id": "cli", "ref": "defaultspack.cli_surface"},
                {"id": "frontend", "ref": "defaultspack.frontend"},
            ],
            "edges": [
                {"id": "cli_to_frontend", "from": "cli.surface", "to": "frontend.surface"},
            ],
        }
    )


def test_startup_node_override_rewrites_edge_source_and_adds_instance():
    graph = _startup_graph()
    nodes = _nodes(
        {
            "node_id": "defaultspack.cli_surface",
            "ports": [{"id": "surface", "direction": "output", "standards": ["rumi.surface"]}],
        },
        {
            "node_id": "defaultspack.frontend",
            "ports": [{"id": "surface", "direction": "input", "standards": ["rumi.surface"]}],
        },
        {
            "node_id": "frontendpack.web_surface",
            "ports": [{"id": "surface", "direction": "output", "standards": ["rumi.surface"]}],
        },
    )

    rewritten, diagnostics = apply_startup_node_overrides(
        graph,
        startup_profile={"node_overrides": {"frontend.surface": "frontendpack.web_surface"}},
        nodes=nodes,
    )

    assert diagnostics == []
    assert rewritten.edges[0].source.to_string() == "frontendpack_web_surface.surface"
    assert any(node.id == "frontendpack_web_surface" and node.ref == "frontendpack.web_surface" for node in rewritten.nodes)
    assert rewritten.metadata["startup_override_node_refs"] == ["frontendpack.web_surface"]


def test_startup_node_override_reports_incompatible_node():
    graph = _startup_graph()
    nodes = _nodes(
        {
            "node_id": "defaultspack.cli_surface",
            "ports": [{"id": "surface", "direction": "output", "standards": ["rumi.surface"]}],
        },
        {
            "node_id": "defaultspack.frontend",
            "ports": [{"id": "surface", "direction": "input", "standards": ["rumi.surface"]}],
        },
        {
            "node_id": "toolpack.tool",
            "ports": [{"id": "tools", "direction": "output", "standards": ["rumi.tool.bundle"]}],
        },
    )

    rewritten, diagnostics = apply_startup_node_overrides(
        graph,
        startup_profile={"node_overrides": {"frontend.surface": "toolpack.tool"}},
        nodes=nodes,
    )

    assert rewritten.edges[0].source.to_string() == "cli.surface"
    assert diagnostics[0]["code"] == "startup_override_no_compatible_output"


def test_startup_node_override_selects_ambiguous_output_deterministically():
    graph = _startup_graph()
    nodes = _nodes(
        {
            "node_id": "defaultspack.cli_surface",
            "ports": [{"id": "surface", "direction": "output", "standards": ["rumi.surface"]}],
        },
        {
            "node_id": "defaultspack.frontend",
            "ports": [{"id": "surface", "direction": "input", "standards": ["rumi.surface"]}],
        },
        {
            "node_id": "frontendpack.web_surface",
            "ports": [
                {"id": "z_surface", "direction": "output", "standards": ["rumi.surface"]},
                {"id": "surface", "direction": "output", "standards": ["rumi.surface"]},
            ],
        },
    )

    rewritten, diagnostics = apply_startup_node_overrides(
        graph,
        startup_profile={"node_overrides": {"frontend.surface": "frontendpack.web_surface"}},
        nodes=nodes,
    )

    assert rewritten.edges[0].source.to_string() == "frontendpack_web_surface.surface"
    assert diagnostics[0]["code"] == "startup_override_ambiguous_output"
    assert diagnostics[0]["selected_port"] == "surface"


def test_profile_extension_only_adds_override_node_refs_from_allowed_packs():
    graph = load_graph_document(
        {
            "version": "rumi.graph.v1",
            "graph_id": "defaultspack.startup",
            "nodes": [
                {"id": "frontendpack_web_surface", "ref": "frontendpack.web_surface"},
                {"id": "frontendpack_tool", "ref": "frontendpack.tool"},
            ],
            "edges": [],
            "metadata": {"startup_override_node_refs": ["frontendpack.web_surface"]},
        }
    )
    profile = CapabilityProfileDefinition(
        profile_id="defaultspack.startup",
        enabled_nodes=["defaultspack.frontend"],
    )

    extended = extend_profile_for_startup_overrides(
        profile,
        startup_profile={"packs": ["defaultspack", "frontendpack"]},
        graph=graph,
    )

    assert "frontendpack.web_surface" in extended.enabled_nodes
    assert "frontendpack.tool" not in extended.enabled_nodes
    assert extended.metadata["startup_override_nodes"] == ["frontendpack.web_surface"]
