"""
Node definition models for Capability Graph nodes.

The core runtime keeps these models domain-neutral: validation is limited to
node shape, port direction, standards, and legacy field normalization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


NODE_SPEC_VERSION = "rumi.node.v1"
CORE_START_NODE_ID = "rumi.start"
CORE_START_STANDARD = "rumi.flow.start"

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_PORT_DIRECTIONS = frozenset({"input", "output", "bidirectional"})
_STANDARD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+$")


class NodeValidationError(ValueError):
    """Raised when a node definition cannot be normalized or validated."""


@dataclass(frozen=True)
class PortDefinition:
    id: str
    direction: str
    standards: List[str]
    display_name: Dict[str, str] = field(default_factory=dict)
    description: Dict[str, str] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    multiple: bool = False
    required: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PortDefinition":
        if not isinstance(data, Mapping):
            raise NodeValidationError("port must be an object")

        port_id = _require_id(data.get("id"), "port.id")
        direction = data.get("direction")
        if direction not in _PORT_DIRECTIONS:
            raise NodeValidationError(
                f"port '{port_id}' has invalid direction: {direction!r}"
            )

        standards = data.get("standards")
        if standards is None and data.get("contracts") is not None:
            standards = data.get("contracts")
        legacy_contract = data.get("contract")
        if standards is None and legacy_contract is not None:
            standards = [legacy_contract]
        standards = _normalize_standards(standards, f"port '{port_id}'")

        return cls(
            id=port_id,
            direction=str(direction),
            standards=standards,
            display_name=_normalize_i18n(data.get("display_name")),
            description=_normalize_i18n(data.get("description")),
            aliases=_normalize_string_list(data.get("aliases"), "aliases"),
            multiple=bool(data.get("multiple", False)),
            required=bool(data.get("required", False)),
        )

    def display_label(self, locale: str = "en") -> str:
        return (
            self.display_name.get(locale)
            or self.display_name.get("en")
            or self.id
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "direction": self.direction,
            "display_name": dict(self.display_name),
            "description": dict(self.description),
            "standards": list(self.standards),
            "aliases": list(self.aliases),
            "multiple": self.multiple,
            "required": self.required,
        }


@dataclass(frozen=True)
class BindingDefinition:
    compile: Optional[str] = None
    on_input: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any) -> "BindingDefinition":
        if data in (None, {}):
            return cls()
        if not isinstance(data, Mapping):
            raise NodeValidationError("bindings must be an object")
        compile_handler = data.get("compile")
        if compile_handler is not None and not isinstance(compile_handler, str):
            raise NodeValidationError("bindings.compile must be a string")
        on_input_raw = data.get("on_input", {})
        if not isinstance(on_input_raw, Mapping):
            raise NodeValidationError("bindings.on_input must be an object")
        on_input: Dict[str, str] = {}
        for port_id, handler_id in on_input_raw.items():
            if not isinstance(port_id, str) or not isinstance(handler_id, str):
                raise NodeValidationError("bindings.on_input entries must be string pairs")
            on_input[port_id] = handler_id
        return cls(compile=compile_handler, on_input=on_input)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.compile:
            data["compile"] = self.compile
        if self.on_input:
            data["on_input"] = dict(self.on_input)
        return data


@dataclass(frozen=True)
class NodeDefinition:
    node_id: str
    kind: str = "ecosystem.component"
    display_name: Dict[str, str] = field(default_factory=dict)
    description: Dict[str, str] = field(default_factory=dict)
    ports: List[PortDefinition] = field(default_factory=list)
    bindings: BindingDefinition = field(default_factory=BindingDefinition)
    requirements: Dict[str, Any] = field(default_factory=dict)
    permissions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        source_path: Optional[str] = None,
        pack_id: Optional[str] = None,
    ) -> "NodeDefinition":
        if not isinstance(data, Mapping):
            raise NodeValidationError("node must be an object")

        node_id = _require_id(data.get("node_id"), "node_id")
        if node_id.startswith("rumi.") and node_id != CORE_START_NODE_ID:
            raise NodeValidationError(
                f"core-owned node id '{node_id}' is not loadable from ecosystem packs"
            )

        display_name = _normalize_i18n(data.get("display_name"))
        legacy_name = data.get("name")
        if legacy_name and "en" not in display_name:
            if not isinstance(legacy_name, str):
                raise NodeValidationError("name must be a string")
            display_name["en"] = legacy_name

        ports_raw = data.get("ports", [])
        if not isinstance(ports_raw, list):
            raise NodeValidationError(f"node '{node_id}' ports must be a list")
        ports = [PortDefinition.from_dict(port) for port in ports_raw]
        _validate_unique_ports(node_id, ports)

        metadata = _normalize_object(data.get("metadata"), "metadata")
        if pack_id and "pack_id" not in metadata:
            metadata["pack_id"] = pack_id
        if source_path and "source_path" not in metadata:
            metadata["source_path"] = source_path

        return cls(
            node_id=node_id,
            kind=str(data.get("kind") or "ecosystem.component"),
            display_name=display_name,
            description=_normalize_i18n(data.get("description")),
            ports=ports,
            bindings=BindingDefinition.from_dict(data.get("bindings")),
            requirements=_normalize_object(data.get("requirements"), "requirements"),
            permissions=_normalize_object(data.get("permissions"), "permissions"),
            metadata=metadata,
        )

    def display_label(self, locale: str = "en") -> str:
        return (
            self.display_name.get(locale)
            or self.display_name.get("en")
            or self.node_id
        )

    def get_port(self, port_id: str) -> Optional[PortDefinition]:
        for port in self.ports:
            if port.id == port_id:
                return port
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "display_name": dict(self.display_name),
            "description": dict(self.description),
            "ports": [port.to_dict() for port in self.ports],
            "bindings": self.bindings.to_dict(),
            "requirements": dict(self.requirements),
            "permissions": dict(self.permissions),
            "metadata": dict(self.metadata),
        }


def make_core_start_node() -> NodeDefinition:
    """Return the core-owned built-in start node registered before discovery."""
    return NodeDefinition(
        node_id=CORE_START_NODE_ID,
        kind="core.builtin",
        display_name={"en": "Start", "ja": "開始"},
        description={
            "en": "Core-owned graph start node.",
            "ja": "core が所有するグラフ開始ノード。",
        },
        ports=[
            PortDefinition(
                id="out",
                direction="output",
                display_name={"en": "Out", "ja": "出力"},
                standards=[CORE_START_STANDARD],
                multiple=True,
                required=False,
            )
        ],
        metadata={"owner": "core", "builtin": True},
    )


def load_node_document(
    data: Mapping[str, Any],
    *,
    source_path: Optional[str] = None,
    pack_id: Optional[str] = None,
) -> List[NodeDefinition]:
    """Normalize a rumi.node.v1 document containing one or many nodes."""
    if not isinstance(data, Mapping):
        raise NodeValidationError("node document must be an object")
    version = data.get("version")
    if version != NODE_SPEC_VERSION:
        raise NodeValidationError(f"unsupported node document version: {version!r}")
    nodes_raw = data.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise NodeValidationError("node document must contain a non-empty nodes list")
    return [
        NodeDefinition.from_dict(node, source_path=source_path, pack_id=pack_id)
        for node in nodes_raw
    ]


def _require_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise NodeValidationError(f"{field_name} must be a non-empty string")
    if not _ID_RE.match(value):
        raise NodeValidationError(f"{field_name} has invalid characters: {value!r}")
    return value


def _normalize_i18n(value: Any) -> Dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, str):
        return {"en": value}
    if not isinstance(value, Mapping):
        raise NodeValidationError("i18n text must be a string or object")
    result: Dict[str, str] = {}
    for locale, text in value.items():
        if not isinstance(locale, str) or not isinstance(text, str):
            raise NodeValidationError("i18n text entries must be string pairs")
        if locale:
            result[locale] = text
    return result


def _normalize_string_list(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise NodeValidationError(f"{field_name} must be a list")
    result: List[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise NodeValidationError(f"{field_name} entries must be non-empty strings")
        result.append(item)
    return result


def _normalize_standards(value: Any, label: str) -> List[str]:
    standards = _normalize_string_list(value, "standards")
    if not standards:
        raise NodeValidationError(f"{label} must declare at least one standard")
    seen = set()
    result: List[str] = []
    for standard in standards:
        if not _STANDARD_RE.match(standard):
            raise NodeValidationError(f"{label} has invalid standard: {standard!r}")
        if standard not in seen:
            seen.add(standard)
            result.append(standard)
    return result


def _normalize_object(value: Any, field_name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise NodeValidationError(f"{field_name} must be an object")
    return dict(value)


def _validate_unique_ports(node_id: str, ports: List[PortDefinition]) -> None:
    seen = set()
    for port in ports:
        if port.id in seen:
            raise NodeValidationError(f"node '{node_id}' has duplicate port id '{port.id}'")
        seen.add(port.id)
