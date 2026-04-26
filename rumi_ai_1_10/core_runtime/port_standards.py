"""Domain-neutral Capability Graph port validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .graph_models import GraphDefinition, GraphEdge, GraphEndpoint
from .node_models import NodeDefinition, PortDefinition
from .profile_models import ProfileDefinition


@dataclass
class GraphValidationResult:
    ok: bool
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "diagnostics": list(self.diagnostics),
        }


def validate_graph_ports(
    graph: GraphDefinition,
    *,
    nodes: Dict[str, NodeDefinition],
    profile: Optional[ProfileDefinition] = None,
) -> GraphValidationResult:
    diagnostics: List[Dict[str, Any]] = []
    instances = {instance.id: instance for instance in graph.nodes}
    incoming_by_target: Dict[str, int] = {}

    for instance in graph.nodes:
        node = nodes.get(instance.ref)
        if node is None:
            _diagnose(
                diagnostics,
                "error",
                "missing_node_ref",
                f"Graph node '{instance.id}' references unknown node '{instance.ref}'",
                graph_node_id=instance.id,
                node_ref=instance.ref,
            )
            continue
        if profile is not None and not profile.is_node_enabled(instance.ref):
            _diagnose(
                diagnostics,
                "error",
                "profile_node_unavailable",
                f"Node '{instance.ref}' is not enabled for profile '{profile.profile_id}'",
                graph_node_id=instance.id,
                node_ref=instance.ref,
                profile_id=profile.profile_id,
            )

    for edge in graph.edges:
        source_node, source_port = _resolve_endpoint(
            edge.source,
            instances=instances,
            nodes=nodes,
            edge=edge,
            role="source",
            diagnostics=diagnostics,
        )
        target_node, target_port = _resolve_endpoint(
            edge.target,
            instances=instances,
            nodes=nodes,
            edge=edge,
            role="target",
            diagnostics=diagnostics,
        )
        if source_node is None or target_node is None or source_port is None or target_port is None:
            continue
        if source_port.direction != "output":
            _diagnose(
                diagnostics,
                "error",
                "invalid_source_direction",
                f"Edge '{edge.id}' source port '{edge.source.to_string()}' must be output",
                edge_id=edge.id,
                port_direction=source_port.direction,
            )
        if target_port.direction != "input":
            _diagnose(
                diagnostics,
                "error",
                "invalid_target_direction",
                f"Edge '{edge.id}' target port '{edge.target.to_string()}' must be input",
                edge_id=edge.id,
                port_direction=target_port.direction,
            )
        if not set(source_port.standards).intersection(target_port.standards):
            _diagnose(
                diagnostics,
                "error",
                "standards_mismatch",
                f"Edge '{edge.id}' ports do not share a standard",
                edge_id=edge.id,
                source_standards=list(source_port.standards),
                target_standards=list(target_port.standards),
            )
        target_key = edge.target.to_string()
        incoming_by_target[target_key] = incoming_by_target.get(target_key, 0) + 1
        if not target_port.multiple and incoming_by_target[target_key] > 1:
            _diagnose(
                diagnostics,
                "error",
                "input_multiple_violation",
                f"Input port '{target_key}' does not allow multiple incoming edges",
                edge_id=edge.id,
                endpoint=target_key,
            )

    connected_inputs = set(incoming_by_target)
    for instance in graph.nodes:
        node = nodes.get(instance.ref)
        if node is None:
            continue
        for port in node.ports:
            endpoint = f"{instance.id}.{port.id}"
            if port.direction == "input" and port.required and endpoint not in connected_inputs:
                _diagnose(
                    diagnostics,
                    "error",
                    "required_input_missing",
                    f"Required input port '{endpoint}' has no incoming edge",
                    graph_node_id=instance.id,
                    node_ref=instance.ref,
                    port_id=port.id,
                )

    return GraphValidationResult(
        ok=not any(item.get("level") == "error" for item in diagnostics),
        diagnostics=diagnostics,
    )


def _resolve_endpoint(
    endpoint: GraphEndpoint,
    *,
    instances: Dict[str, Any],
    nodes: Dict[str, NodeDefinition],
    edge: GraphEdge,
    role: str,
    diagnostics: List[Dict[str, Any]],
) -> tuple[Optional[NodeDefinition], Optional[PortDefinition]]:
    instance = instances.get(endpoint.node_id)
    if instance is None:
        _diagnose(
            diagnostics,
            "error",
            "missing_endpoint_node",
            f"Edge '{edge.id}' {role} references unknown graph node '{endpoint.node_id}'",
            edge_id=edge.id,
            endpoint=endpoint.to_string(),
        )
        return None, None
    node = nodes.get(instance.ref)
    if node is None:
        return None, None
    port = node.get_port(endpoint.port_id)
    if port is None:
        _diagnose(
            diagnostics,
            "error",
            "missing_port",
            f"Edge '{edge.id}' {role} references missing port '{endpoint.to_string()}'",
            edge_id=edge.id,
            endpoint=endpoint.to_string(),
            node_ref=instance.ref,
            port_id=endpoint.port_id,
        )
    return node, port


def _diagnose(
    diagnostics: List[Dict[str, Any]],
    level: str,
    code: str,
    message: str,
    **meta: Any,
) -> None:
    diagnostics.append(
        {
            "level": level,
            "code": code,
            "message": message,
            **meta,
        }
    )
