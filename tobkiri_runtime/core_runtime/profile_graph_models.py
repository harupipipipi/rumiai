from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


PROFILE_GRAPH_VERSION = 1
PROFILE_GRAPH_SELECTED_CATEGORIES = (
    "tools",
    "webhooks",
    "api_routes",
    "prompts",
    "frontend",
    "flows",
    "nodes",
    "ai_input_nodes",
    "gates",
)


@dataclass(frozen=True)
class ProfileGraphNode:
    id: str
    kind: str
    label: str = ""
    ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "ref": self.ref,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProfileGraphEdge:
    id: str
    from_id: str
    to_id: str
    kind: str
    active: bool = True
    from_port: str = ""
    to_port: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "kind": self.kind,
            "active": self.active,
            "from_port": self.from_port,
            "to_port": self.to_port,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProfileGraphDocument:
    version: int
    profile_id: str
    nodes: list[ProfileGraphNode]
    edges: list[ProfileGraphEdge]
    selected: dict[str, list[str] | dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile_id": self.profile_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "selected": {
                category: list(value) if isinstance(value, list) else dict(value)
                for category, value in self.selected.items()
            },
        }

    def persisted_graph_payload(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def normalize_profile_graph_document(
    profile_id: str,
    raw_graph: Any = None,
    raw_selected: Any = None,
    *,
    strict: bool = False,
) -> Tuple[ProfileGraphDocument, List[Dict[str, Any]]]:
    diagnostics: List[Dict[str, Any]] = []
    graph = raw_graph if isinstance(raw_graph, dict) else {}

    nodes = _normalize_nodes(graph.get("nodes"), diagnostics, strict=strict)
    node_ids = {node.id for node in nodes}
    edges = _normalize_edges(graph.get("edges"), node_ids, diagnostics, strict=strict)

    selected_source = raw_selected if isinstance(raw_selected, dict) else graph.get("selected")
    selected = normalize_profile_graph_selected(selected_source)

    document = ProfileGraphDocument(
        version=int(graph.get("version") or PROFILE_GRAPH_VERSION),
        profile_id=str(profile_id or "").strip(),
        nodes=nodes,
        edges=edges,
        selected=selected,
    )
    return document, diagnostics


def normalize_profile_graph_selected(value: Any) -> dict[str, list[str] | dict[str, Any]]:
    selected = value if isinstance(value, dict) else {}
    normalized: dict[str, list[str] | dict[str, Any]] = {}
    for category in PROFILE_GRAPH_SELECTED_CATEGORIES:
        normalized[category] = _normalize_string_list(selected.get(category))
    for key, entry in selected.items():
        key_name = str(key or "").strip()
        if not key_name or key_name in normalized:
            continue
        if isinstance(entry, dict):
            normalized[key_name] = dict(entry)
    return normalized


def empty_profile_graph_document(profile_id: str) -> ProfileGraphDocument:
    selected: dict[str, list[str] | dict[str, Any]] = {
        category: [] for category in PROFILE_GRAPH_SELECTED_CATEGORIES
    }
    return ProfileGraphDocument(
        version=PROFILE_GRAPH_VERSION,
        profile_id=str(profile_id or "").strip(),
        nodes=[],
        edges=[],
        selected=selected,
    )


def _normalize_nodes(value: Any, diagnostics: List[Dict[str, Any]], *, strict: bool) -> list[ProfileGraphNode]:
    if value is None:
        return []
    if not isinstance(value, list):
        if strict:
            raise ValueError("graph.nodes must be a list")
        diagnostics.append(_diagnostic("warning", "profile_graph_nodes_invalid", "graph.nodes must be a list"))
        return []

    nodes: list[ProfileGraphNode] = []
    seen_ids: set[str] = set()
    for index, raw_node in enumerate(value):
        if not isinstance(raw_node, dict):
            if strict:
                raise ValueError(f"graph.nodes[{index}] must be an object")
            diagnostics.append(
                _diagnostic("warning", "profile_graph_node_invalid", f"graph.nodes[{index}] must be an object")
            )
            continue
        node_id = str(raw_node.get("id") or "").strip()
        kind = str(raw_node.get("kind") or "").strip()
        if not node_id or not kind:
            if strict:
                raise ValueError(f"graph.nodes[{index}] requires id and kind")
            diagnostics.append(
                _diagnostic("warning", "profile_graph_node_missing_fields", f"graph.nodes[{index}] requires id and kind")
            )
            continue
        if node_id in seen_ids:
            if strict:
                raise ValueError(f"graph.nodes contains duplicate id '{node_id}'")
            diagnostics.append(
                _diagnostic("warning", "profile_graph_node_duplicate", f"graph.nodes contains duplicate id '{node_id}'")
            )
            continue
        seen_ids.add(node_id)
        metadata = raw_node.get("metadata")
        nodes.append(
            ProfileGraphNode(
                id=node_id,
                kind=kind,
                label=str(raw_node.get("label") or "").strip(),
                ref=str(raw_node.get("ref") or "").strip(),
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
            )
        )
    return nodes


def _normalize_edges(
    value: Any,
    node_ids: set[str],
    diagnostics: List[Dict[str, Any]],
    *,
    strict: bool,
) -> list[ProfileGraphEdge]:
    if value is None:
        return []
    if not isinstance(value, list):
        if strict:
            raise ValueError("graph.edges must be a list")
        diagnostics.append(_diagnostic("warning", "profile_graph_edges_invalid", "graph.edges must be a list"))
        return []

    edges: list[ProfileGraphEdge] = []
    seen_ids: set[str] = set()
    for index, raw_edge in enumerate(value):
        if not isinstance(raw_edge, dict):
            if strict:
                raise ValueError(f"graph.edges[{index}] must be an object")
            diagnostics.append(
                _diagnostic("warning", "profile_graph_edge_invalid", f"graph.edges[{index}] must be an object")
            )
            continue
        edge_id = str(raw_edge.get("id") or "").strip()
        from_id = str(raw_edge.get("from_id") or raw_edge.get("from") or "").strip()
        to_id = str(raw_edge.get("to_id") or raw_edge.get("to") or "").strip()
        kind = str(raw_edge.get("kind") or "").strip()
        if not edge_id or not from_id or not to_id or not kind:
            if strict:
                raise ValueError(f"graph.edges[{index}] requires id, from_id, to_id, and kind")
            diagnostics.append(
                _diagnostic(
                    "warning",
                    "profile_graph_edge_missing_fields",
                    f"graph.edges[{index}] requires id, from_id, to_id, and kind",
                )
            )
            continue
        if edge_id in seen_ids:
            if strict:
                raise ValueError(f"graph.edges contains duplicate id '{edge_id}'")
            diagnostics.append(
                _diagnostic("warning", "profile_graph_edge_duplicate", f"graph.edges contains duplicate id '{edge_id}'")
            )
            continue
        if from_id not in node_ids or to_id not in node_ids:
            if strict:
                raise ValueError(f"graph.edges[{index}] references missing nodes")
            diagnostics.append(
                _diagnostic(
                    "warning",
                    "profile_graph_edge_missing_nodes",
                    f"graph.edges[{index}] references nodes that are not present in graph.nodes",
                )
            )
            continue
        seen_ids.add(edge_id)
        metadata = raw_edge.get("metadata")
        edge_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        edges.append(
            ProfileGraphEdge(
                id=edge_id,
                from_id=from_id,
                to_id=to_id,
                kind=kind,
                active=bool(raw_edge.get("active", True)),
                from_port=str(raw_edge.get("from_port") or edge_metadata.get("from_port") or "").strip(),
                to_port=str(raw_edge.get("to_port") or edge_metadata.get("to_port") or "").strip(),
                metadata=edge_metadata,
            )
        )
    return edges


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _diagnostic(level: str, code: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "message": message}
