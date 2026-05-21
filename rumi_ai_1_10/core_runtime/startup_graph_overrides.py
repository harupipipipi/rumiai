"""Apply Startup Profile node overrides to Capability Graph definitions."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .graph_models import GraphDefinition, GraphEdge, GraphEndpoint, GraphNodeInstance
from .node_models import NodeDefinition, PortDefinition


def apply_startup_node_overrides(
    graph: GraphDefinition,
    *,
    startup_profile: Dict[str, Any],
    nodes: Dict[str, NodeDefinition],
) -> Tuple[GraphDefinition, List[Dict[str, Any]]]:
    """Return a graph copy whose matching edge sources reflect startup overrides."""
    overrides = startup_profile.get("node_overrides")
    if not isinstance(overrides, dict) or not overrides:
        return graph, []

    diagnostics: List[Dict[str, Any]] = []
    instances_by_id = {instance.id: instance for instance in graph.nodes}
    instance_id_by_ref = {instance.ref: instance.id for instance in graph.nodes}
    graph_nodes = list(graph.nodes)
    graph_edges: List[GraphEdge] = []
    changed = False

    for edge in graph.edges:
        override_ref = overrides.get(edge.target.to_string())
        if not isinstance(override_ref, str) or not override_ref.strip():
            graph_edges.append(edge)
            continue
        override_ref = override_ref.strip()
        override_node = nodes.get(override_ref)
        if override_node is None:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "startup_override_node_missing",
                    f"Startup override node '{override_ref}' was not found",
                    edge_id=edge.id,
                    port_key=edge.target.to_string(),
                    node_ref=override_ref,
                )
            )
            graph_edges.append(edge)
            continue

        target_instance = instances_by_id.get(edge.target.node_id)
        target_node = nodes.get(target_instance.ref) if target_instance else None
        target_port = target_node.get_port(edge.target.port_id) if target_node else None
        if target_port is None:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "startup_override_target_port_missing",
                    f"Startup override target port '{edge.target.to_string()}' was not found",
                    edge_id=edge.id,
                    port_key=edge.target.to_string(),
                )
            )
            graph_edges.append(edge)
            continue

        output_port = choose_compatible_output_port(
            override_node,
            target_port,
            preferred_port_id=edge.source.port_id,
            diagnostics=diagnostics,
            edge_id=edge.id,
            port_key=edge.target.to_string(),
        )
        if output_port is None:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "startup_override_no_compatible_output",
                    f"Startup override node '{override_ref}' has no compatible output for '{edge.target.to_string()}'",
                    edge_id=edge.id,
                    port_key=edge.target.to_string(),
                    node_ref=override_ref,
                    target_standards=list(target_port.standards),
                )
            )
            graph_edges.append(edge)
            continue

        source_instance_id = instance_id_by_ref.get(override_ref)
        if source_instance_id is None:
            source_instance_id = _graph_instance_id(override_ref, instances_by_id)
            instance = GraphNodeInstance(id=source_instance_id, ref=override_ref)
            graph_nodes.append(instance)
            instances_by_id[source_instance_id] = instance
            instance_id_by_ref[override_ref] = source_instance_id
        graph_edges.append(
            GraphEdge(
                id=edge.id,
                source=GraphEndpoint(source_instance_id, output_port.id),
                target=edge.target,
                kind=edge.kind,
                metadata=dict(edge.metadata),
            )
        )
        changed = True

    if not changed:
        return graph, diagnostics
    return (
        GraphDefinition(
            graph_id=graph.graph_id,
            display_name=dict(graph.display_name),
            description=dict(graph.description),
            nodes=graph_nodes,
            edges=graph_edges,
            metadata=dict(graph.metadata),
        ),
        diagnostics,
    )


def choose_compatible_output_port(
    override_node: NodeDefinition,
    target_port: PortDefinition,
    *,
    preferred_port_id: str = "",
    diagnostics: List[Dict[str, Any]] | None = None,
    edge_id: str = "",
    port_key: str = "",
) -> PortDefinition | None:
    compatible = [
        port
        for port in override_node.ports
        if port.direction == "output"
        and set(port.standards).intersection(target_port.standards)
    ]
    if not compatible:
        return None
    selected = sorted(
        compatible,
        key=lambda port: (
            0 if port.id == preferred_port_id else 1,
            _preferred_port_rank(port.id),
            port.id,
        ),
    )[0]
    if len(compatible) > 1 and diagnostics is not None:
        diagnostics.append(
            _diagnostic(
                "warning",
                "startup_override_ambiguous_output",
                f"Startup override node '{override_node.node_id}' has multiple compatible outputs; selected '{selected.id}'",
                edge_id=edge_id,
                port_key=port_key,
                node_ref=override_node.node_id,
                selected_port=selected.id,
                compatible_ports=sorted(port.id for port in compatible),
            )
        )
    return selected


def _graph_instance_id(node_ref: str, existing: Dict[str, GraphNodeInstance]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", node_ref).strip("_") or "override_node"
    if not re.match(r"^[A-Za-z]", base):
        base = f"node_{base}"
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def _preferred_port_rank(port_id: str) -> int:
    preferred = ("surface", "client", "tools", "memory", "prompt", "out", "ui", "cli")
    try:
        return preferred.index(port_id)
    except ValueError:
        return len(preferred)


def _diagnostic(level: str, code: str, message: str, **meta: Any) -> Dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        **meta,
    }
