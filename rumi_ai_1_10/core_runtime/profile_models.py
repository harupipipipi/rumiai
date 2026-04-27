"""
Capability Profile models for Capability Graph runtime/workspace presets.

Capability profiles are intentionally separate from StartupProfileManager.
Existing startup profiles remain the launch-time source of truth until a later
explicit bridge or migration PR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


PROFILE_SPEC_VERSION = "rumi.profile.v1"

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


class ProfileValidationError(ValueError):
    """Raised when a Capability Graph profile cannot be normalized."""


@dataclass(frozen=True)
class CapabilityProfileDefinition:
    profile_id: str
    kind: str = "runtime_profile"
    locale: Optional[str] = None
    display_name: Dict[str, str] = field(default_factory=dict)
    description: Dict[str, str] = field(default_factory=dict)
    default_graph: Optional[str] = None
    default_flow: Optional[str] = None
    surfaces: Dict[str, Any] = field(default_factory=dict)
    permissions: Dict[str, Any] = field(default_factory=dict)
    enabled_nodes: List[str] = field(default_factory=list)
    disabled_nodes: List[str] = field(default_factory=list)
    node_settings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    policy: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        source_path: Optional[str] = None,
        pack_id: Optional[str] = None,
        source_type: str = "user",
    ) -> "CapabilityProfileDefinition":
        if not isinstance(data, Mapping):
            raise ProfileValidationError("profile must be an object")
        version = data.get("version")
        if version != PROFILE_SPEC_VERSION:
            raise ProfileValidationError(f"unsupported profile version: {version!r}")

        profile_id = _require_id(data.get("profile_id"), "profile_id")
        display_name = _normalize_i18n(data.get("display_name"))
        legacy_name = data.get("name")
        if legacy_name and "en" not in display_name:
            if not isinstance(legacy_name, str):
                raise ProfileValidationError("name must be a string")
            display_name["en"] = legacy_name

        metadata = _normalize_object(data.get("metadata"), "metadata")
        if pack_id:
            metadata.setdefault("pack_id", pack_id)
        if source_path:
            metadata.setdefault("source_path", source_path)
        metadata.setdefault("source_type", source_type)

        return cls(
            profile_id=profile_id,
            kind=str(data.get("kind") or "runtime_profile"),
            locale=_optional_string(data.get("locale"), "locale"),
            display_name=display_name,
            description=_normalize_i18n(data.get("description")),
            default_graph=_optional_string(data.get("default_graph"), "default_graph"),
            default_flow=_optional_string(data.get("default_flow"), "default_flow"),
            surfaces=_normalize_object(data.get("surfaces"), "surfaces"),
            permissions=_normalize_object(data.get("permissions"), "permissions"),
            enabled_nodes=_normalize_id_list(data.get("enabled_nodes"), "enabled_nodes"),
            disabled_nodes=_normalize_id_list(data.get("disabled_nodes"), "disabled_nodes"),
            node_settings=_normalize_node_settings(data.get("node_settings")),
            policy=_normalize_object(data.get("policy"), "policy"),
            metadata=metadata,
        )

    def display_label(self, locale: str = "en") -> str:
        return (
            self.display_name.get(locale)
            or self.display_name.get("en")
            or self.profile_id
        )

    def is_node_enabled(self, node_id: str) -> bool:
        if node_id in self.disabled_nodes:
            return False
        if not self.enabled_nodes:
            return True
        return node_id in self.enabled_nodes or node_id == "rumi.start"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "kind": self.kind,
            "locale": self.locale,
            "display_name": dict(self.display_name),
            "description": dict(self.description),
            "default_graph": self.default_graph,
            "default_flow": self.default_flow,
            "surfaces": dict(self.surfaces),
            "permissions": dict(self.permissions),
            "enabled_nodes": list(self.enabled_nodes),
            "disabled_nodes": list(self.disabled_nodes),
            "node_settings": {key: dict(value) for key, value in self.node_settings.items()},
            "policy": dict(self.policy),
            "metadata": dict(self.metadata),
        }


def load_profile_document(
    data: Mapping[str, Any],
    *,
    source_path: Optional[str] = None,
    pack_id: Optional[str] = None,
    source_type: str = "user",
) -> CapabilityProfileDefinition:
    return CapabilityProfileDefinition.from_dict(
        data,
        source_path=source_path,
        pack_id=pack_id,
        source_type=source_type,
    )


# Compatibility alias for the initial Capability Graph PRs. New code should use
# CapabilityProfileDefinition to keep it distinct from StartupProfileManager's
# launch-time startup profiles.
ProfileDefinition = CapabilityProfileDefinition


def _require_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProfileValidationError(f"{field_name} must be a non-empty string")
    if not _ID_RE.match(value):
        raise ProfileValidationError(f"{field_name} has invalid characters: {value!r}")
    return value


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileValidationError(f"{field_name} must be a string")
    return value


def _normalize_i18n(value: Any) -> Dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, str):
        return {"en": value}
    if not isinstance(value, Mapping):
        raise ProfileValidationError("i18n text must be a string or object")
    result: Dict[str, str] = {}
    for locale, text in value.items():
        if not isinstance(locale, str) or not isinstance(text, str):
            raise ProfileValidationError("i18n text entries must be string pairs")
        if locale:
            result[locale] = text
    return result


def _normalize_object(value: Any, field_name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ProfileValidationError(f"{field_name} must be an object")
    return dict(value)


def _normalize_id_list(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileValidationError(f"{field_name} must be a list")
    result: List[str] = []
    for item in value:
        result.append(_require_id(item, field_name))
    return result


def _normalize_node_settings(value: Any) -> Dict[str, Dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ProfileValidationError("node_settings must be an object")
    result: Dict[str, Dict[str, Any]] = {}
    for node_id, settings in value.items():
        normalized_id = _require_id(node_id, "node_settings key")
        if not isinstance(settings, Mapping):
            raise ProfileValidationError("node_settings entries must be objects")
        result[normalized_id] = dict(settings)
    return result
