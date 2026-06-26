from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 1
COMPILER_VERSION = "recursive-ui-compiler-pr1.3"
DEFAULT_VIEWPORTS = [390, 768, 1024, 1440]
DEFAULT_TEXT_SCALES = [1, 1.25, 2]
DEFAULT_SCENARIOS = ["default", "long", "empty", "loading", "error"]
NODE_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
IMPLEMENTATION_MODES = {
    "group-only",
    "component",
    "component-with-slots",
    "repeated-component",
    "composition-only",
}
DENSITIES = {"comfortable", "compact", "dataDense", "data-dense"}
HEIGHT_BEHAVIORS = {"content", "fixed", "fill", "scroll"}
MOBILE_BEHAVIORS = {"stack", "sticky-bottom", "route", "sheet", "drawer", "hide"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_id(value: str) -> str:
    raw = str(value or "").strip()
    if not NODE_ID_RE.fullmatch(raw):
        raise ValueError(f"invalid node id: {raw!r}")
    return raw


def _camel_or_snake(data: dict[str, Any], snake: str, camel: str, default: Any = None) -> Any:
    if snake in data:
        return data.get(snake)
    if camel in data:
        return data.get(camel)
    return default


def _limited_string(value: Any, *, field_name: str, max_length: int) -> str:
    raw = str(value or "").strip()
    if len(raw) > max_length:
        raise ValueError(f"{field_name} exceeds {max_length} characters")
    return raw


def _string_list(value: Any, *, field_name: str, max_items: int, max_length: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    if len(value) > max_items:
        raise ValueError(f"{field_name} exceeds {max_items} items")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("id")
        raw = _limited_string(item, field_name=field_name, max_length=max_length)
        if not raw:
            raise ValueError(f"{field_name} contains an empty item")
        if raw.lower() in seen:
            raise ValueError(f"{field_name} contains duplicate item: {raw}")
        seen.add(raw.lower())
        result.append(raw)
    return result


def _non_negative_int(value: Any, *, field_name: str, default: int = 0, max_value: int = 1000) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if parsed < 0 or parsed > max_value:
        raise ValueError(f"{field_name} must be between 0 and {max_value}")
    return parsed


def _positive_int(value: Any, *, field_name: str, default: int, min_value: int = 1, max_value: int = 1000) -> int:
    parsed = _non_negative_int(value, field_name=field_name, default=default, max_value=max_value)
    if parsed < min_value:
        raise ValueError(f"{field_name} must be at least {min_value}")
    return parsed


def _finite_float(
    value: Any,
    *,
    field_name: str,
    default: float,
    min_value: float,
    max_value: float,
) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if not math.isfinite(parsed) or parsed < min_value or parsed > max_value:
        raise ValueError(f"{field_name} must be between {min_value} and {max_value}")
    return parsed


def _int_list(value: Any, *, field_name: str, default: list[int], max_items: int) -> list[int]:
    if value is None:
        return list(default)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    if len(value) > max_items:
        raise ValueError(f"{field_name} exceeds {max_items} items")
    result = [
        _positive_int(item, field_name=field_name, default=0, min_value=1, max_value=4096)
        for item in value
    ]
    return result or list(default)


def _float_list(value: Any, *, field_name: str, default: list[float], max_items: int) -> list[float]:
    if value is None:
        return list(default)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    if len(value) > max_items:
        raise ValueError(f"{field_name} exceeds {max_items} items")
    result = [
        _finite_float(item, field_name=field_name, default=1, min_value=0.5, max_value=2)
        for item in value
    ]
    return result or list(default)


@dataclass(frozen=True)
class ResourceLimits:
    max_input_depth: int = 12
    max_plan_depth: int = 6
    max_input_nodes: int = 500
    max_generated_nodes: int = 500
    max_children_per_node: int = 8
    max_split_fanout: int = 6
    max_string_length: int = 240
    max_list_length: int = 64
    max_candidate_count: int = 4
    max_slots_per_node: int = 8
    max_ownership_groups_per_node: int = 32
    max_metadata_bytes: int = 8192
    max_metadata_depth: int = 4
    max_metadata_keys: int = 32
    max_metadata_string_length: int = 240

    def to_dict(self) -> dict[str, int]:
        return {
            "maxInputDepth": self.max_input_depth,
            "maxPlanDepth": self.max_plan_depth,
            "maxInputNodes": self.max_input_nodes,
            "maxGeneratedNodes": self.max_generated_nodes,
            "maxChildrenPerNode": self.max_children_per_node,
            "maxSplitFanout": self.max_split_fanout,
            "maxStringLength": self.max_string_length,
            "maxListLength": self.max_list_length,
            "maxCandidateCount": self.max_candidate_count,
            "maxSlotsPerNode": self.max_slots_per_node,
            "maxOwnershipGroupsPerNode": self.max_ownership_groups_per_node,
            "maxMetadataBytes": self.max_metadata_bytes,
            "maxMetadataDepth": self.max_metadata_depth,
            "maxMetadataKeys": self.max_metadata_keys,
            "maxMetadataStringLength": self.max_metadata_string_length,
        }


@dataclass(frozen=True)
class TrustedCompilerPolicy:
    generation: dict[str, Any] = field(
        default_factory=lambda: {
            "mode": "recursive-zero-to-one",
            "rootMayWriteUi": False,
            "regenerateInsteadOfPatch": True,
            "isolateAgents": "worktree",
        }
    )
    quality: dict[str, Any] = field(
        default_factory=lambda: {
            "rejectUnverified": True,
            "rejectPrimaryTruncation": True,
            "rejectHorizontalOverflow": True,
            "rejectArbitraryTokens": True,
            "maxCompressionScore": 0.35,
        }
    )
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": dict(self.generation),
            "quality": dict(self.quality),
            "resourceLimits": self.resource_limits.to_dict(),
        }


@dataclass(frozen=True)
class LayoutEnvelope:
    min_width: int = 0
    preferred_width: int | None = None
    max_width: int | None = None
    height_behavior: str = "content"
    mobile_behavior: str = "stack"

    @classmethod
    def from_dict(cls, value: Any) -> "LayoutEnvelope":
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("layoutEnvelope must be an object")
        min_width = _non_negative_int(
            _camel_or_snake(value, "min_width", "minWidth"),
            field_name="layoutEnvelope.minWidth",
            default=0,
            max_value=10000,
        )
        preferred_raw = _camel_or_snake(value, "preferred_width", "preferredWidth")
        max_raw = _camel_or_snake(value, "max_width", "maxWidth")
        preferred = (
            _non_negative_int(preferred_raw, field_name="layoutEnvelope.preferredWidth", max_value=10000)
            if preferred_raw is not None
            else None
        )
        max_width = (
            _non_negative_int(max_raw, field_name="layoutEnvelope.maxWidth", max_value=10000)
            if max_raw is not None
            else None
        )
        if preferred is not None and preferred < min_width:
            raise ValueError("layoutEnvelope preferredWidth must be >= minWidth")
        if max_width is not None:
            if max_width < min_width:
                raise ValueError("layoutEnvelope maxWidth must be >= minWidth")
            if preferred is not None and max_width < preferred:
                raise ValueError("layoutEnvelope maxWidth must be >= preferredWidth")
        height_behavior = str(
            _camel_or_snake(value, "height_behavior", "heightBehavior", "content") or "content"
        )
        mobile_behavior = str(
            _camel_or_snake(value, "mobile_behavior", "mobileBehavior", "stack") or "stack"
        )
        if height_behavior not in HEIGHT_BEHAVIORS:
            raise ValueError(f"invalid heightBehavior: {height_behavior}")
        if mobile_behavior not in MOBILE_BEHAVIORS:
            raise ValueError(f"invalid mobileBehavior: {mobile_behavior}")
        return cls(
            min_width=min_width,
            preferred_width=preferred,
            max_width=max_width,
            height_behavior=height_behavior,
            mobile_behavior=mobile_behavior,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "minWidth": self.min_width,
            "preferredWidth": self.preferred_width,
            "maxWidth": self.max_width,
            "heightBehavior": self.height_behavior,
            "mobileBehavior": self.mobile_behavior,
        }


@dataclass(frozen=True)
class SlotDefinition:
    id: str
    purpose: str = ""
    accepts_node_id: str | None = None
    required: bool = True
    min_width: int = 0
    preferred_width: int | None = None
    max_width: int | None = None

    @classmethod
    def from_dict(cls, value: Any, *, limits: ResourceLimits) -> "SlotDefinition":
        if not isinstance(value, dict):
            raise ValueError("slot must be an object")
        _reject_unknown_keys(
            value,
            {
                "id",
                "purpose",
                "acceptsNodeId",
                "accepts_node_id",
                "required",
                "minWidth",
                "min_width",
                "preferredWidth",
                "preferred_width",
                "maxWidth",
                "max_width",
                "layoutEnvelope",
                "layout_envelope",
                "heightBehavior",
                "height_behavior",
                "mobileBehavior",
                "mobile_behavior",
            },
            "slot",
        )
        envelope = LayoutEnvelope.from_dict(value.get("layoutEnvelope") or value)
        accepts_raw = _camel_or_snake(value, "accepts_node_id", "acceptsNodeId")
        accepts_node_id = canonical_id(str(accepts_raw)) if accepts_raw not in (None, "") else None
        required_raw = value.get("required")
        if required_raw is None:
            required = True
        elif isinstance(required_raw, bool):
            required = required_raw
        else:
            raise ValueError("slot.required must be a boolean")
        return cls(
            id=canonical_id(str(value.get("id") or "")),
            purpose=_limited_string(
                value.get("purpose"), field_name="slot.purpose", max_length=limits.max_string_length
            ),
            accepts_node_id=accepts_node_id,
            required=required,
            min_width=envelope.min_width,
            preferred_width=envelope.preferred_width,
            max_width=envelope.max_width,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "purpose": self.purpose,
            "acceptsNodeId": self.accepts_node_id,
            "required": self.required,
            "minWidth": self.min_width,
            "preferredWidth": self.preferred_width,
            "maxWidth": self.max_width,
        }


@dataclass(frozen=True)
class ResponsibilitySet:
    visual_roles: list[str] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    mutations: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    layout_algorithms: list[str] = field(default_factory=list)
    responsive_topologies: list[str] = field(default_factory=list)
    shared: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Any, *, limits: ResourceLimits) -> "ResponsibilitySet":
        data = value if isinstance(value, dict) else {}
        return cls(
            visual_roles=_responsibility_ids(
                data.get("visualRoles") or data.get("visual_roles"),
                field_name="responsibilities.visualRoles",
                limits=limits,
            ),
            controls=_responsibility_ids(
                data.get("controls"),
                field_name="responsibilities.controls",
                limits=limits,
            ),
            mutations=_responsibility_ids(
                data.get("mutations"),
                field_name="responsibilities.mutations",
                limits=limits,
            ),
            states=_responsibility_ids(
                data.get("states"),
                field_name="responsibilities.states",
                limits=limits,
            ),
            layout_algorithms=_responsibility_ids(
                data.get("layoutAlgorithms") or data.get("layout_algorithms"),
                field_name="responsibilities.layoutAlgorithms",
                limits=limits,
            ),
            responsive_topologies=_responsibility_ids(
                data.get("responsiveTopologies") or data.get("responsive_topologies"),
                field_name="responsibilities.responsiveTopologies",
                limits=limits,
            ),
            shared=_responsibility_ids(
                data.get("shared"),
                field_name="responsibilities.shared",
                limits=limits,
            ),
        )

    def merged_with_node_fields(self, *, inputs: list[str], events: list[str], states: list[str]) -> "ResponsibilitySet":
        return ResponsibilitySet(
            visual_roles=list(self.visual_roles),
            controls=_unique([*self.controls, *inputs, *events]),
            mutations=list(self.mutations),
            states=_unique([*self.states, *states]),
            layout_algorithms=list(self.layout_algorithms),
            responsive_topologies=list(self.responsive_topologies),
            shared=list(self.shared),
        )

    def has_any(self) -> bool:
        return bool(
            self.visual_roles
            or self.controls
            or self.mutations
            or self.states
            or self.layout_algorithms
            or self.responsive_topologies
        )

    def expected_complexity(self) -> "ComplexitySignals":
        return ComplexitySignals(
            unique_visual_roles=len(self.visual_roles),
            interactive_controls=len(self.controls),
            meaningful_states=len(self.states),
            async_mutations=len(self.mutations),
            responsive_topologies=max(1, len(self.responsive_topologies)),
            special_layout_algorithms=len(self.layout_algorithms),
        )

    def categories(self) -> dict[str, list[str]]:
        return {
            "visualRoles": list(self.visual_roles),
            "controls": list(self.controls),
            "mutations": list(self.mutations),
            "states": list(self.states),
            "layoutAlgorithms": list(self.layout_algorithms),
            "responsiveTopologies": list(self.responsive_topologies),
        }

    def all_ids(self) -> set[str]:
        ids: set[str] = set()
        for values in self.categories().values():
            ids.update(values)
        return ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "visualRoles": list(self.visual_roles),
            "controls": list(self.controls),
            "mutations": list(self.mutations),
            "states": list(self.states),
            "layoutAlgorithms": list(self.layout_algorithms),
            "responsiveTopologies": list(self.responsive_topologies),
            "shared": list(self.shared),
        }


def _responsibility_ids(value: Any, *, field_name: str, limits: ResourceLimits) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    if len(value) > limits.max_list_length:
        raise ValueError(f"{field_name} exceeds {limits.max_list_length} items")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("id")
        raw = _limited_string(item, field_name=field_name, max_length=limits.max_string_length)
        if not raw:
            raise ValueError(f"{field_name} contains an empty id")
        if raw.lower() in seen:
            raise ValueError(f"{field_name} contains duplicate id: {raw}")
        seen.add(raw.lower())
        result.append(raw)
    return result


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _reject_duplicate_slot_ids(slots: list[SlotDefinition]) -> None:
    seen: set[str] = set()
    for slot in slots:
        key = slot.id.casefold()
        if key in seen:
            raise ValueError(f"slots contain duplicate id: {slot.id}")
        seen.add(key)


@dataclass(frozen=True)
class OwnershipGroup:
    id: str
    controls: list[str] = field(default_factory=list)
    mutations: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Any, *, limits: ResourceLimits) -> "OwnershipGroup":
        if not isinstance(value, dict):
            raise ValueError("ownership group must be an object")
        return cls(
            id=canonical_id(str(value.get("id") or "")),
            controls=_responsibility_ids(value.get("controls"), field_name="ownership.controls", limits=limits),
            mutations=_responsibility_ids(value.get("mutations"), field_name="ownership.mutations", limits=limits),
            states=_responsibility_ids(value.get("states"), field_name="ownership.states", limits=limits),
        )

    def all_ids(self) -> set[str]:
        return {*self.controls, *self.mutations, *self.states}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "controls": list(self.controls),
            "mutations": list(self.mutations),
            "states": list(self.states),
        }


@dataclass(frozen=True)
class ComplexitySignals:
    unique_visual_roles: int = 0
    interactive_controls: int = 0
    meaningful_states: int = 0
    async_mutations: int = 0
    responsive_topologies: int = 1
    special_layout_algorithms: int = 0

    @classmethod
    def from_dict(cls, value: Any) -> "ComplexitySignals":
        data = value if isinstance(value, dict) else {}
        nested = data.get("complexity") if isinstance(data.get("complexity"), dict) else data
        return cls(
            unique_visual_roles=_non_negative_int(
                _camel_or_snake(nested, "unique_visual_roles", "uniqueVisualRoles"),
                field_name="complexity.uniqueVisualRoles",
            ),
            interactive_controls=_non_negative_int(
                _camel_or_snake(nested, "interactive_controls", "interactiveControls"),
                field_name="complexity.interactiveControls",
            ),
            meaningful_states=_non_negative_int(
                _camel_or_snake(nested, "meaningful_states", "meaningfulStates"),
                field_name="complexity.meaningfulStates",
            ),
            async_mutations=_non_negative_int(
                _camel_or_snake(nested, "async_mutations", "asyncMutations"),
                field_name="complexity.asyncMutations",
            ),
            responsive_topologies=_positive_int(
                _camel_or_snake(nested, "responsive_topologies", "responsiveTopologies", 1),
                field_name="complexity.responsiveTopologies",
                default=1,
                max_value=12,
            ),
            special_layout_algorithms=_non_negative_int(
                _camel_or_snake(nested, "special_layout_algorithms", "specialLayoutAlgorithms"),
                field_name="complexity.specialLayoutAlgorithms",
                max_value=12,
            ),
        )

    @classmethod
    def from_responsibilities(cls, responsibilities: ResponsibilitySet) -> "ComplexitySignals":
        return responsibilities.expected_complexity()

    def to_dict(self) -> dict[str, int]:
        return {
            "uniqueVisualRoles": self.unique_visual_roles,
            "interactiveControls": self.interactive_controls,
            "meaningfulStates": self.meaningful_states,
            "asyncMutations": self.async_mutations,
            "responsiveTopologies": self.responsive_topologies,
            "specialLayoutAlgorithms": self.special_layout_algorithms,
        }


@dataclass(frozen=True)
class LeafBudget:
    max_complexity: float = 28.0
    max_visual_roles: int = 18
    max_interactive_controls: int = 5
    max_mutations: int = 1
    max_responsive_topologies: int = 2
    max_special_layout_algorithms: int = 1
    min_visual_roles: int = 2

    @classmethod
    def from_dict(cls, value: Any) -> "LeafBudget":
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("leafBudget must be an object")
        return cls(
            max_complexity=_finite_float(
                _camel_or_snake(value, "max_complexity", "maxComplexity"),
                field_name="leafBudget.maxComplexity",
                default=cls.max_complexity,
                min_value=8,
                max_value=80,
            ),
            max_visual_roles=_positive_int(
                _camel_or_snake(value, "max_visual_roles", "maxVisualRoles"),
                field_name="leafBudget.maxVisualRoles",
                default=cls.max_visual_roles,
                max_value=40,
            ),
            max_interactive_controls=_positive_int(
                _camel_or_snake(value, "max_interactive_controls", "maxInteractiveControls"),
                field_name="leafBudget.maxInteractiveControls",
                default=cls.max_interactive_controls,
                max_value=20,
            ),
            max_mutations=_positive_int(
                _camel_or_snake(value, "max_mutations", "maxMutations"),
                field_name="leafBudget.maxMutations",
                default=cls.max_mutations,
                max_value=10,
            ),
            max_responsive_topologies=_positive_int(
                _camel_or_snake(value, "max_responsive_topologies", "maxResponsiveTopologies"),
                field_name="leafBudget.maxResponsiveTopologies",
                default=cls.max_responsive_topologies,
                max_value=6,
            ),
            max_special_layout_algorithms=_positive_int(
                _camel_or_snake(value, "max_special_layout_algorithms", "maxSpecialLayoutAlgorithms"),
                field_name="leafBudget.maxSpecialLayoutAlgorithms",
                default=cls.max_special_layout_algorithms,
                max_value=6,
            ),
            min_visual_roles=_positive_int(
                _camel_or_snake(value, "min_visual_roles", "minVisualRoles"),
                field_name="leafBudget.minVisualRoles",
                default=cls.min_visual_roles,
                max_value=12,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "maxComplexity": self.max_complexity,
            "maxVisualRoles": self.max_visual_roles,
            "maxInteractiveControls": self.max_interactive_controls,
            "maxMutations": self.max_mutations,
            "maxResponsiveTopologies": self.max_responsive_topologies,
            "maxSpecialLayoutAlgorithms": self.max_special_layout_algorithms,
            "minVisualRoles": self.min_visual_roles,
        }


@dataclass(frozen=True)
class CandidateBudget:
    foundation: int = 3
    page_frame: int = 2
    primary_region: int = 2
    repeated_core_component: int = 2
    secondary_region: int = 1

    @classmethod
    def from_dict(cls, value: Any, *, limits: ResourceLimits) -> "CandidateBudget":
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("candidates must be an object")

        def candidate_count(key: str, camel: str, default: int) -> int:
            return _positive_int(
                _camel_or_snake(value, key, camel),
                field_name=f"candidates.{camel}",
                default=default,
                max_value=limits.max_candidate_count,
            )

        return cls(
            foundation=candidate_count("foundation", "foundation", cls.foundation),
            page_frame=candidate_count("page_frame", "pageFrame", cls.page_frame),
            primary_region=candidate_count("primary_region", "primaryRegion", cls.primary_region),
            repeated_core_component=candidate_count(
                "repeated_core_component",
                "repeatedCoreComponent",
                cls.repeated_core_component,
            ),
            secondary_region=candidate_count("secondary_region", "secondaryRegion", cls.secondary_region),
        )

    def for_importance(self, importance: str) -> int:
        normalized = str(importance or "").strip().lower().replace("-", "_")
        if normalized in {"page_frame", "pageframe"}:
            return self.page_frame
        if normalized in {"primary_region", "primaryregion"}:
            return self.primary_region
        if normalized in {"repeated_core_component", "repeatedcorecomponent"}:
            return self.repeated_core_component
        if normalized == "foundation":
            return self.foundation
        return self.secondary_region

    def to_dict(self) -> dict[str, int]:
        return {
            "foundation": self.foundation,
            "pageFrame": self.page_frame,
            "primaryRegion": self.primary_region,
            "repeatedCoreComponent": self.repeated_core_component,
            "secondaryRegion": self.secondary_region,
        }


@dataclass(frozen=True)
class UICompilerConfig:
    trusted_policy: TrustedCompilerPolicy = field(default_factory=TrustedCompilerPolicy)
    leaf_budget: LeafBudget = field(default_factory=LeafBudget)
    candidates: CandidateBudget = field(default_factory=CandidateBudget)
    viewports: list[int] = field(default_factory=lambda: list(DEFAULT_VIEWPORTS))
    text_scales: list[float] = field(default_factory=lambda: list(DEFAULT_TEXT_SCALES))
    scenarios: list[str] = field(default_factory=lambda: list(DEFAULT_SCENARIOS))

    @property
    def resource_limits(self) -> ResourceLimits:
        return self.trusted_policy.resource_limits

    @classmethod
    def from_dict(cls, value: Any) -> "UICompilerConfig":
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("config must be an object")
        _reject_unknown_keys(
            value,
            {
                "leafBudget",
                "leaf_budget",
                "candidates",
                "viewports",
                "textScales",
                "text_scales",
                "scenarios",
                "generation",
                "quality",
            },
            "config",
        )
        policy = TrustedCompilerPolicy()
        _reject_trusted_policy_overrides(value, policy)
        limits = policy.resource_limits
        return cls(
            trusted_policy=policy,
            leaf_budget=LeafBudget.from_dict(_camel_or_snake(value, "leaf_budget", "leafBudget")),
            candidates=CandidateBudget.from_dict(value.get("candidates"), limits=limits),
            viewports=_int_list(value.get("viewports"), field_name="viewports", default=DEFAULT_VIEWPORTS, max_items=8),
            text_scales=_float_list(
                _camel_or_snake(value, "text_scales", "textScales"),
                field_name="textScales",
                default=DEFAULT_TEXT_SCALES,
                max_items=6,
            ),
            scenarios=_string_list(
                value.get("scenarios"),
                field_name="scenarios",
                max_items=12,
                max_length=limits.max_string_length,
            )
            or list(DEFAULT_SCENARIOS),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "compilerVersion": COMPILER_VERSION,
            "trustedPolicy": self.trusted_policy.to_dict(),
            "leafBudget": self.leaf_budget.to_dict(),
            "candidates": self.candidates.to_dict(),
            "viewports": list(self.viewports),
            "textScales": list(self.text_scales),
            "scenarios": list(self.scenarios),
        }


def _reject_trusted_policy_overrides(value: dict[str, Any], policy: TrustedCompilerPolicy) -> None:
    generation = value.get("generation")
    if generation is not None:
        if not isinstance(generation, dict):
            raise ValueError("generation must be an object")
        _reject_unknown_keys(generation, set(policy.generation), "generation")
        for key, trusted_value in policy.generation.items():
            if key in generation and generation[key] != trusted_value:
                raise ValueError(f"generation.{key} is a trusted compiler policy and cannot be overridden")
    quality = value.get("quality")
    if quality is not None:
        if not isinstance(quality, dict):
            raise ValueError("quality must be an object")
        _reject_unknown_keys(quality, set(policy.quality), "quality")
        for key, trusted_value in policy.quality.items():
            if key in quality and quality[key] != trusted_value:
                raise ValueError(f"quality.{key} is a trusted compiler policy and cannot be overridden")


def _reject_unknown_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(str(key) for key in value if str(key) not in allowed)
    if unknown:
        raise ValueError(f"{label} contains unsupported keys: {', '.join(unknown)}")


def _validate_metadata(value: Any, *, limits: ResourceLimits) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("metadata must be an object")
    key_count = 0

    def visit(current: Any, *, depth: int, field_name: str) -> Any:
        nonlocal key_count
        if depth > limits.max_metadata_depth:
            raise ValueError("metadata exceeds max depth")
        if isinstance(current, dict):
            key_count += len(current)
            if key_count > limits.max_metadata_keys:
                raise ValueError("metadata exceeds max key count")
            result: dict[str, Any] = {}
            for raw_key, raw_value in current.items():
                if not isinstance(raw_key, str):
                    raise ValueError("metadata keys must be strings")
                key = _limited_string(
                    raw_key,
                    field_name=f"{field_name}.key",
                    max_length=limits.max_metadata_string_length,
                )
                if not key:
                    raise ValueError("metadata contains an empty key")
                result[key] = visit(raw_value, depth=depth + 1, field_name=f"{field_name}.{key}")
            return result
        if isinstance(current, list):
            if len(current) > limits.max_list_length:
                raise ValueError("metadata list exceeds max list length")
            return [
                visit(item, depth=depth + 1, field_name=f"{field_name}[]")
                for item in current
            ]
        if isinstance(current, str):
            return _limited_string(
                current,
                field_name=field_name,
                max_length=limits.max_metadata_string_length,
            )
        if isinstance(current, bool) or current is None or isinstance(current, int):
            return current
        if isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError("metadata numbers must be finite")
            return current
        raise ValueError("metadata must contain only JSON scalar, object, or list values")

    metadata = visit(value, depth=0, field_name="metadata")
    encoded = json.dumps(
        metadata,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > limits.max_metadata_bytes:
        raise ValueError("metadata exceeds max byte size")
    return metadata


@dataclass(frozen=True)
class UINode:
    id: str
    purpose: str = ""
    density: str = "comfortable"
    primary_perceptual_task: str = ""
    importance: str = "secondaryRegion"
    implementation_mode: str = "component"
    complexity: ComplexitySignals = field(default_factory=ComplexitySignals)
    layout_envelope: LayoutEnvelope = field(default_factory=LayoutEnvelope)
    responsibilities: ResponsibilitySet = field(default_factory=ResponsibilitySet)
    ownership: list[OwnershipGroup] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    required_states: list[str] = field(default_factory=list)
    allowed_primitives: list[str] = field(default_factory=list)
    visible_action_budget: int = 3
    slots: list[SlotDefinition] = field(default_factory=list)
    children: list["UINode"] = field(default_factory=list)
    split_hints: list["UINode"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        value: Any,
        *,
        limits: ResourceLimits | None = None,
        depth: int = 0,
        counter: list[int] | None = None,
    ) -> "UINode":
        limits = limits or ResourceLimits()
        if depth > limits.max_input_depth:
            raise ValueError("UI tree exceeds max input depth")
        if not isinstance(value, dict):
            raise ValueError("UI node must be an object")
        _reject_unknown_keys(
            value,
            {
                "id",
                "purpose",
                "density",
                "primaryPerceptualTask",
                "primary_perceptual_task",
                "importance",
                "candidateKind",
                "implementationMode",
                "implementation_mode",
                "complexity",
                "layoutEnvelope",
                "layout_envelope",
                "responsibilities",
                "ownership",
                "inputs",
                "events",
                "requiredStates",
                "required_states",
                "allowedPrimitives",
                "allowed_primitives",
                "visibleActionBudget",
                "visible_action_budget",
                "slots",
                "children",
                "splitHints",
                "split_hints",
                "decompositionHints",
                "decomposition_hints",
                "metadata",
            },
            "ui_tree",
        )
        counter = counter if counter is not None else [0]
        counter[0] += 1
        if counter[0] > limits.max_input_nodes:
            raise ValueError("UI tree exceeds max input nodes")

        node_id = canonical_id(str(value.get("id") or ""))
        children_value = value.get("children", [])
        hints_value = (
            value.get("split_hints")
            or value.get("splitHints")
            or value.get("decomposition_hints")
            or value.get("decompositionHints")
            or []
        )
        if not isinstance(children_value, list):
            raise ValueError("children must be a list")
        if not isinstance(hints_value, list):
            raise ValueError("splitHints must be a list")
        if len(children_value) > limits.max_children_per_node:
            raise ValueError("children exceeds max children per node")
        if len(hints_value) > limits.max_children_per_node:
            raise ValueError("splitHints exceeds max children per node")
        children = [
            cls.from_dict(item, limits=limits, depth=depth + 1, counter=counter)
            for item in children_value
        ]
        split_hints = [
            cls.from_dict(item, limits=limits, depth=depth + 1, counter=counter)
            for item in hints_value
        ]
        inputs = _string_list(
            value.get("inputs"),
            field_name=f"{node_id}.inputs",
            max_items=limits.max_list_length,
            max_length=limits.max_string_length,
        )
        events = _string_list(
            value.get("events"),
            field_name=f"{node_id}.events",
            max_items=limits.max_list_length,
            max_length=limits.max_string_length,
        )
        required_states = _string_list(
            _camel_or_snake(value, "required_states", "requiredStates"),
            field_name=f"{node_id}.requiredStates",
            max_items=limits.max_list_length,
            max_length=limits.max_string_length,
        )
        responsibilities = ResponsibilitySet.from_dict(value.get("responsibilities"), limits=limits)
        responsibilities = responsibilities.merged_with_node_fields(
            inputs=inputs,
            events=events,
            states=required_states,
        )
        complexity = ComplexitySignals.from_responsibilities(responsibilities)
        explicit_complexity = ComplexitySignals.from_dict(value)
        complexity = ComplexitySignals(
            unique_visual_roles=max(complexity.unique_visual_roles, explicit_complexity.unique_visual_roles),
            interactive_controls=max(complexity.interactive_controls, explicit_complexity.interactive_controls),
            meaningful_states=max(complexity.meaningful_states, explicit_complexity.meaningful_states),
            async_mutations=max(complexity.async_mutations, explicit_complexity.async_mutations),
            responsive_topologies=explicit_complexity.responsive_topologies,
            special_layout_algorithms=explicit_complexity.special_layout_algorithms,
        )
        density = str(value.get("density") or "comfortable").strip()
        if density not in DENSITIES:
            raise ValueError(f"invalid density: {density}")
        mode = str(
            value.get("implementationMode")
            or value.get("implementation_mode")
            or ("group-only" if children else "component")
        )
        if mode not in IMPLEMENTATION_MODES:
            raise ValueError(f"invalid implementationMode: {mode}")
        slots_value = value.get("slots", [])
        if slots_value is None:
            slots_value = []
        if not isinstance(slots_value, list):
            raise ValueError("slots must be a list")
        if len(slots_value) > limits.max_slots_per_node:
            raise ValueError("slots exceeds max slots per node")
        slots = [
            SlotDefinition.from_dict(item, limits=limits)
            for item in slots_value
        ]
        _reject_duplicate_slot_ids(slots)
        if slots and mode not in {"component-with-slots", "composition-only"}:
            raise ValueError("slots require component-with-slots or composition-only implementationMode")
        if mode == "component-with-slots" and not slots:
            raise ValueError("component-with-slots requires slots")
        ownership_value = value.get("ownership", [])
        if ownership_value is None:
            ownership_value = []
        if not isinstance(ownership_value, list):
            raise ValueError("ownership must be a list")
        if len(ownership_value) > limits.max_ownership_groups_per_node:
            raise ValueError("ownership exceeds max ownership groups per node")
        return cls(
            id=node_id,
            purpose=_limited_string(
                value.get("purpose"), field_name=f"{node_id}.purpose", max_length=limits.max_string_length
            ),
            density=density,
            primary_perceptual_task=_limited_string(
                _camel_or_snake(value, "primary_perceptual_task", "primaryPerceptualTask", ""),
                field_name=f"{node_id}.primaryPerceptualTask",
                max_length=limits.max_string_length,
            ),
            importance=_limited_string(
                value.get("importance") or value.get("candidateKind") or "secondaryRegion",
                field_name=f"{node_id}.importance",
                max_length=80,
            ),
            implementation_mode=mode,
            complexity=complexity,
            layout_envelope=LayoutEnvelope.from_dict(
                _camel_or_snake(value, "layout_envelope", "layoutEnvelope")
            ),
            responsibilities=responsibilities,
            ownership=[
                OwnershipGroup.from_dict(item, limits=limits)
                for item in ownership_value
            ],
            inputs=inputs,
            events=events,
            required_states=required_states,
            allowed_primitives=_string_list(
                _camel_or_snake(value, "allowed_primitives", "allowedPrimitives"),
                field_name=f"{node_id}.allowedPrimitives",
                max_items=limits.max_list_length,
                max_length=limits.max_string_length,
            ),
            visible_action_budget=_positive_int(
                _camel_or_snake(value, "visible_action_budget", "visibleActionBudget"),
                field_name=f"{node_id}.visibleActionBudget",
                default=3,
                max_value=20,
            ),
            slots=slots,
            children=children,
            split_hints=split_hints,
            metadata=_validate_metadata(value.get("metadata"), limits=limits),
        )

    def to_dict(self, *, include_split_hints: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "purpose": self.purpose,
            "density": self.density,
            "primaryPerceptualTask": self.primary_perceptual_task,
            "importance": self.importance,
            "implementationMode": self.implementation_mode,
            "complexity": self.complexity.to_dict(),
            "layoutEnvelope": self.layout_envelope.to_dict(),
            "responsibilities": self.responsibilities.to_dict(),
            "ownership": [item.to_dict() for item in self.ownership],
            "inputs": list(self.inputs),
            "events": list(self.events),
            "requiredStates": list(self.required_states),
            "allowedPrimitives": list(self.allowed_primitives),
            "visibleActionBudget": self.visible_action_budget,
            "slots": [slot.to_dict() for slot in self.slots],
            "children": [
                child.to_dict(include_split_hints=include_split_hints) for child in self.children
            ],
            "metadata": dict(self.metadata),
        }
        if include_split_hints:
            result["splitHints"] = [
                hint.to_dict(include_split_hints=True) for hint in self.split_hints
            ]
        return result


@dataclass(frozen=True)
class ComponentContract:
    id: str
    purpose: str
    primary_perceptual_task: str
    density: str
    implementation_mode: str
    layout_envelope: LayoutEnvelope
    responsibilities: ResponsibilitySet
    ownership: list[OwnershipGroup] = field(default_factory=list)
    slots: list[SlotDefinition] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    required_states: list[str] = field(default_factory=list)
    allowed_primitives: list[str] = field(default_factory=list)
    visible_action_budget: int = 3
    candidate_count: int = 1
    complexity_score: float = 0.0
    source_node_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_node(
        cls,
        node: UINode,
        *,
        complexity_score: float,
        candidate_count: int,
    ) -> "ComponentContract":
        return cls(
            id=node.id,
            purpose=node.purpose,
            primary_perceptual_task=node.primary_perceptual_task or node.purpose,
            density=node.density,
            implementation_mode=node.implementation_mode,
            layout_envelope=node.layout_envelope,
            responsibilities=node.responsibilities,
            ownership=list(node.ownership),
            slots=list(node.slots),
            inputs=list(node.inputs),
            events=list(node.events),
            required_states=list(node.required_states),
            allowed_primitives=list(node.allowed_primitives),
            visible_action_budget=node.visible_action_budget,
            candidate_count=candidate_count,
            complexity_score=round(float(complexity_score), 2),
            source_node_id=node.id,
            metadata=dict(node.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "id": self.id,
            "purpose": self.purpose,
            "primaryPerceptualTask": self.primary_perceptual_task,
            "density": self.density,
            "implementationMode": self.implementation_mode,
            "layoutEnvelope": self.layout_envelope.to_dict(),
            "responsibilities": self.responsibilities.to_dict(),
            "ownership": [item.to_dict() for item in self.ownership],
            "slots": [slot.to_dict() for slot in self.slots],
            "slotMappings": [
                {"slotId": slot.id, "nodeId": slot.accepts_node_id}
                for slot in self.slots
                if slot.accepts_node_id
            ],
            "inputs": list(self.inputs),
            "events": list(self.events),
            "requiredStates": list(self.required_states),
            "allowedPrimitives": list(self.allowed_primitives),
            "visibleActionBudget": self.visible_action_budget,
            "candidateCount": self.candidate_count,
            "complexityScore": self.complexity_score,
            "sourceNodeId": self.source_node_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PlanningDiagnostic:
    code: str
    message: str
    node_id: str
    severity: str = "info"
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "nodeId": self.node_id,
            "severity": self.severity,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class PlannedNode:
    node: UINode
    complexity_score: float
    budget_violations: list[str] = field(default_factory=list)
    split_reason: str | None = None
    children: list["PlannedNode"] = field(default_factory=list)
    contract: ComponentContract | None = None

    def leaves(self) -> list["PlannedNode"]:
        if not self.children:
            return [self]
        leaves: list[PlannedNode] = []
        for child in self.children:
            leaves.extend(child.leaves())
        return leaves

    def planned_nodes(self) -> list["PlannedNode"]:
        nodes = [self]
        for child in self.children:
            nodes.extend(child.planned_nodes())
        return nodes

    def contracts(self) -> list[ComponentContract]:
        contracts: list[ComponentContract] = []
        if self.contract is not None:
            contracts.append(self.contract)
        for child in self.children:
            contracts.extend(child.contracts())
        return contracts

    def over_budget_leaves(self) -> list["PlannedNode"]:
        return [leaf for leaf in self.leaves() if leaf.budget_violations]

    def unimplemented_leaves(self) -> list["PlannedNode"]:
        return [leaf for leaf in self.leaves() if leaf.contract is None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node.id,
            "purpose": self.node.purpose,
            "density": self.node.density,
            "importance": self.node.importance,
            "implementationMode": self.node.implementation_mode,
            "complexity": self.node.complexity.to_dict(),
            "complexityScore": round(float(self.complexity_score), 2),
            "budgetViolations": list(self.budget_violations),
            "splitReason": self.split_reason,
            "children": [child.to_dict() for child in self.children],
            "contractId": self.contract.id if self.contract else None,
        }


@dataclass(frozen=True)
class UIPlan:
    run_id: str
    root: PlannedNode
    config: UICompilerConfig
    diagnostics: list[PlanningDiagnostic] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def contracts(self) -> list[ComponentContract]:
        return self.root.contracts()

    def over_budget_leaves(self) -> list[PlannedNode]:
        return self.root.over_budget_leaves()

    def unimplemented_leaves(self) -> list[PlannedNode]:
        return self.root.unimplemented_leaves()

    def has_error_diagnostics(self) -> bool:
        return any(item.is_error for item in self.diagnostics)

    def is_executable(self) -> bool:
        return (
            not self.has_error_diagnostics()
            and not self.over_budget_leaves()
            and not self.unimplemented_leaves()
        )

    def to_dict(self) -> dict[str, Any]:
        contracts = self.contracts()
        leaves = self.root.leaves()
        return {
            "schemaVersion": SCHEMA_VERSION,
            "compilerVersion": COMPILER_VERSION,
            "runId": self.run_id,
            "createdAt": self.created_at,
            "executable": self.is_executable(),
            "config": self.config.to_dict(),
            "root": self.root.to_dict(),
            "contracts": [contract.to_dict() for contract in contracts],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "summary": {
                "nodeCount": len(self.root.planned_nodes()),
                "leafCount": len(leaves),
                "contractCount": len(contracts),
                "overBudgetLeafCount": len(self.over_budget_leaves()),
                "unimplementedLeafCount": len(self.unimplemented_leaves()),
                "errorCount": len([item for item in self.diagnostics if item.is_error]),
            },
        }
