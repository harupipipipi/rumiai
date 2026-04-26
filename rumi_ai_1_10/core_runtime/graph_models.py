"""Capability Graph document models."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


GRAPH_SPEC_VERSION = "rumi.graph.v1"

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_EDGE_KINDS = frozenset({"binding"})


class GraphValidationError(ValueError):
    """Raised when a graph document cannot be normalized."""


@dataclass(frozen=True)
class GraphNodeInstance:
    id: str
    ref: str
    display_name: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GraphNodeInstance":
        if not isinstance(data, Mapping):
            raise GraphValidationError("graph node must be an object")
        node_id = _require_id(data.get("id"), "nodes[].id")
        node_ref = _require_id(data.get("ref"), f"node '{node_id}' ref")
        return cls(
            id=node_id,
            ref=node_ref,
            display_name=_normalize_i18n(data.get("display_name")),
            metadata=_normalize_object(data.get("metadata"), "node.metadata"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ref": self.ref,
            "display_name": dict(self.display_name),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GraphEndpoint:
    node_id: str
    port_id: str

    @classmethod
    def parse(cls, value: Any, field_name: str) -> "GraphEndpoint":
        if not isinstance(value, str) or "." not in value:
            raise GraphValidationError(f"{field_name} must use '<node>.<port>' format")
        node_id, port_id = value.rsplit(".", 1)
        return cls(
            node_id=_require_id(node_id, f"{field_name}.node"),
            port_id=_require_id(port_id, f"{field_name}.port"),
        )

    def to_string(self) -> str:
        return f"{self.node_id}.{self.port_id}"


@dataclass(frozen=True)
class GraphEdge:
    id: str
    source: GraphEndpoint
    target: GraphEndpoint
    kind: str = "binding"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GraphEdge":
        if not isinstance(data, Mapping):
            raise GraphValidationError("graph edge must be an object")
        edge_id = _require_id(data.get("id"), "edges[].id")
        kind = data.get("kind", "binding")
        if kind not in _EDGE_KINDS:
            raise GraphValidationError(f"edge '{edge_id}' has unsupported kind: {kind!r}")
        return cls(
            id=edge_id,
            source=GraphEndpoint.parse(data.get("from"), f"edge '{edge_id}' from"),
            target=GraphEndpoint.parse(data.get("to"), f"edge '{edge_id}' to"),
            kind=str(kind),
            metadata=_normalize_object(data.get("metadata"), "edge.metadata"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "from": self.source.to_string(),
            "to": self.target.to_string(),
            "kind": self.kind,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GraphDefinition:
    graph_id: str
    display_name: Dict[str, str] = field(default_factory=dict)
    description: Dict[str, str] = field(default_factory=dict)
    nodes: List[GraphNodeInstance] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        source_path: Optional[str] = None,
        pack_id: Optional[str] = None,
        source_type: str = "unknown",
    ) -> "GraphDefinition":
        if not isinstance(data, Mapping):
            raise GraphValidationError("graph document must be an object")
        version = data.get("version")
        if version != GRAPH_SPEC_VERSION:
            raise GraphValidationError(f"unsupported graph version: {version!r}")

        graph_id = _require_id(data.get("graph_id"), "graph_id")
        display_name = _normalize_i18n(data.get("display_name"))
        legacy_name = data.get("name")
        if legacy_name and "en" not in display_name:
            if not isinstance(legacy_name, str):
                raise GraphValidationError("name must be a string")
            display_name["en"] = legacy_name

        nodes_raw = data.get("nodes")
        if not isinstance(nodes_raw, list) or not nodes_raw:
            raise GraphValidationError("graph must contain a non-empty nodes list")
        edges_raw = data.get("edges", [])
        if not isinstance(edges_raw, list):
            raise GraphValidationError("graph edges must be a list")

        nodes = [GraphNodeInstance.from_dict(node) for node in nodes_raw]
        edges = [GraphEdge.from_dict(edge) for edge in edges_raw]
        _validate_unique_ids("node instance", [node.id for node in nodes])
        _validate_unique_ids("edge", [edge.id for edge in edges])

        metadata = _normalize_object(data.get("metadata"), "metadata")
        if pack_id and "pack_id" not in metadata:
            metadata["pack_id"] = pack_id
        if source_path and "source_path" not in metadata:
            metadata["source_path"] = source_path
        metadata.setdefault("source_type", source_type)

        return cls(
            graph_id=graph_id,
            display_name=display_name,
            description=_normalize_i18n(data.get("description")),
            nodes=nodes,
            edges=edges,
            metadata=metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "display_name": dict(self.display_name),
            "description": dict(self.description),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "metadata": dict(self.metadata),
        }


def load_graph_document(
    data: Mapping[str, Any],
    *,
    source_path: Optional[str] = None,
    pack_id: Optional[str] = None,
    source_type: str = "unknown",
) -> GraphDefinition:
    return GraphDefinition.from_dict(
        data,
        source_path=source_path,
        pack_id=pack_id,
        source_type=source_type,
    )


def _require_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise GraphValidationError(f"{field_name} must be a non-empty string")
    if not _ID_RE.match(value):
        raise GraphValidationError(f"{field_name} has invalid characters: {value!r}")
    return value


def _normalize_i18n(value: Any) -> Dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, str):
        return {"en": value}
    if not isinstance(value, Mapping):
        raise GraphValidationError("i18n text must be a string or object")
    result: Dict[str, str] = {}
    for locale, text in value.items():
        if not isinstance(locale, str) or not isinstance(text, str):
            raise GraphValidationError("i18n text entries must be string pairs")
        if locale:
            result[locale] = text
    return result


def _normalize_object(value: Any, field_name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise GraphValidationError(f"{field_name} must be an object")
    return dict(value)


def _validate_unique_ids(label: str, ids: List[str]) -> None:
    seen: set[str] = set()
    for item_id in ids:
        if item_id in seen:
            raise GraphValidationError(f"duplicate {label} id: {item_id}")
        seen.add(item_id)
