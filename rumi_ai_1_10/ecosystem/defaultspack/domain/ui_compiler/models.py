from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


DEFAULT_VIEWPORTS = [390, 768, 1024, 1440]
DEFAULT_TEXT_SCALES = [1, 1.25, 2]
DEFAULT_SCENARIOS = ["default", "long", "empty", "loading", "error"]


def _camel_or_snake(data: dict[str, Any], snake: str, camel: str, default: Any = None) -> Any:
    if snake in data:
        return data.get(snake)
    if camel in data:
        return data.get(camel)
    return default


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        stripped = str(item or "").strip()
        if stripped:
            result.append(stripped)
    return result


def _non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, parsed)


def _positive_int(value: Any, default: int) -> int:
    parsed = _non_negative_int(value, default)
    return parsed if parsed > 0 else default


def _float_list(value: Any, default: list[float]) -> list[float]:
    if not isinstance(value, list):
        return list(default)
    result: list[float] = []
    for item in value:
        try:
            parsed = float(item)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            result.append(parsed)
    return result or list(default)


def _int_list(value: Any, default: list[int]) -> list[int]:
    if not isinstance(value, list):
        return list(default)
    result: list[int] = []
    for item in value:
        parsed = _non_negative_int(item)
        if parsed > 0:
            result.append(parsed)
    return result or list(default)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class LayoutEnvelope:
    min_width: int = 0
    preferred_width: int | None = None
    max_width: int | None = None
    height_behavior: str = "content"
    mobile_behavior: str = "stack"

    @classmethod
    def from_dict(cls, value: Any) -> "LayoutEnvelope":
        if not isinstance(value, dict):
            return cls()
        preferred = _camel_or_snake(value, "preferred_width", "preferredWidth")
        max_width = _camel_or_snake(value, "max_width", "maxWidth")
        return cls(
            min_width=_non_negative_int(_camel_or_snake(value, "min_width", "minWidth"), 0),
            preferred_width=_non_negative_int(preferred) if preferred is not None else None,
            max_width=_non_negative_int(max_width) if max_width is not None else None,
            height_behavior=str(
                _camel_or_snake(value, "height_behavior", "heightBehavior", "content") or "content"
            ),
            mobile_behavior=str(
                _camel_or_snake(value, "mobile_behavior", "mobileBehavior", "stack") or "stack"
            ),
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
                _camel_or_snake(nested, "unique_visual_roles", "uniqueVisualRoles")
            ),
            interactive_controls=_non_negative_int(
                _camel_or_snake(nested, "interactive_controls", "interactiveControls")
            ),
            meaningful_states=_non_negative_int(
                _camel_or_snake(nested, "meaningful_states", "meaningfulStates")
            ),
            async_mutations=_non_negative_int(
                _camel_or_snake(nested, "async_mutations", "asyncMutations")
            ),
            responsive_topologies=_positive_int(
                _camel_or_snake(nested, "responsive_topologies", "responsiveTopologies", 1),
                1,
            ),
            special_layout_algorithms=_non_negative_int(
                _camel_or_snake(nested, "special_layout_algorithms", "specialLayoutAlgorithms")
            ),
        )

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
        if not isinstance(value, dict):
            return cls()
        return cls(
            max_complexity=float(
                _camel_or_snake(value, "max_complexity", "maxComplexity", cls.max_complexity)
            ),
            max_visual_roles=_positive_int(
                _camel_or_snake(value, "max_visual_roles", "maxVisualRoles", cls.max_visual_roles),
                cls.max_visual_roles,
            ),
            max_interactive_controls=_positive_int(
                _camel_or_snake(
                    value,
                    "max_interactive_controls",
                    "maxInteractiveControls",
                    cls.max_interactive_controls,
                ),
                cls.max_interactive_controls,
            ),
            max_mutations=_positive_int(
                _camel_or_snake(value, "max_mutations", "maxMutations", cls.max_mutations),
                cls.max_mutations,
            ),
            max_responsive_topologies=_positive_int(
                _camel_or_snake(
                    value,
                    "max_responsive_topologies",
                    "maxResponsiveTopologies",
                    cls.max_responsive_topologies,
                ),
                cls.max_responsive_topologies,
            ),
            max_special_layout_algorithms=_positive_int(
                _camel_or_snake(
                    value,
                    "max_special_layout_algorithms",
                    "maxSpecialLayoutAlgorithms",
                    cls.max_special_layout_algorithms,
                ),
                cls.max_special_layout_algorithms,
            ),
            min_visual_roles=_positive_int(
                _camel_or_snake(value, "min_visual_roles", "minVisualRoles", cls.min_visual_roles),
                cls.min_visual_roles,
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
    def from_dict(cls, value: Any) -> "CandidateBudget":
        if not isinstance(value, dict):
            return cls()
        return cls(
            foundation=_positive_int(value.get("foundation"), cls.foundation),
            page_frame=_positive_int(_camel_or_snake(value, "page_frame", "pageFrame"), cls.page_frame),
            primary_region=_positive_int(
                _camel_or_snake(value, "primary_region", "primaryRegion"),
                cls.primary_region,
            ),
            repeated_core_component=_positive_int(
                _camel_or_snake(value, "repeated_core_component", "repeatedCoreComponent"),
                cls.repeated_core_component,
            ),
            secondary_region=_positive_int(
                _camel_or_snake(value, "secondary_region", "secondaryRegion"),
                cls.secondary_region,
            ),
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
    generation: dict[str, Any] = field(
        default_factory=lambda: {
            "mode": "recursive-zero-to-one",
            "rootMayWriteUi": False,
            "regenerateInsteadOfPatch": True,
            "isolateAgents": "worktree",
        }
    )
    leaf_budget: LeafBudget = field(default_factory=LeafBudget)
    candidates: CandidateBudget = field(default_factory=CandidateBudget)
    quality: dict[str, Any] = field(
        default_factory=lambda: {
            "rejectUnverified": True,
            "rejectPrimaryTruncation": True,
            "rejectHorizontalOverflow": True,
            "rejectArbitraryTokens": True,
            "maxCompressionScore": 0.35,
        }
    )
    viewports: list[int] = field(default_factory=lambda: list(DEFAULT_VIEWPORTS))
    text_scales: list[float] = field(default_factory=lambda: list(DEFAULT_TEXT_SCALES))
    scenarios: list[str] = field(default_factory=lambda: list(DEFAULT_SCENARIOS))

    @classmethod
    def from_dict(cls, value: Any) -> "UICompilerConfig":
        if not isinstance(value, dict):
            return cls()
        return cls(
            generation=dict(value.get("generation") or cls().generation),
            leaf_budget=LeafBudget.from_dict(_camel_or_snake(value, "leaf_budget", "leafBudget")),
            candidates=CandidateBudget.from_dict(value.get("candidates")),
            quality=dict(value.get("quality") or cls().quality),
            viewports=_int_list(value.get("viewports"), DEFAULT_VIEWPORTS),
            text_scales=_float_list(_camel_or_snake(value, "text_scales", "textScales"), DEFAULT_TEXT_SCALES),
            scenarios=_string_list(value.get("scenarios")) or list(DEFAULT_SCENARIOS),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": dict(self.generation),
            "leafBudget": self.leaf_budget.to_dict(),
            "candidates": self.candidates.to_dict(),
            "quality": dict(self.quality),
            "viewports": list(self.viewports),
            "textScales": list(self.text_scales),
            "scenarios": list(self.scenarios),
        }


@dataclass(frozen=True)
class UINode:
    id: str
    purpose: str = ""
    density: str = "comfortable"
    primary_perceptual_task: str = ""
    importance: str = "secondaryRegion"
    complexity: ComplexitySignals = field(default_factory=ComplexitySignals)
    layout_envelope: LayoutEnvelope = field(default_factory=LayoutEnvelope)
    inputs: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    required_states: list[str] = field(default_factory=list)
    allowed_primitives: list[str] = field(default_factory=list)
    visible_action_budget: int = 3
    children: list["UINode"] = field(default_factory=list)
    split_hints: list["UINode"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any) -> "UINode":
        if not isinstance(value, dict):
            raise ValueError("UI node must be a dict")
        node_id = str(value.get("id") or "").strip()
        if not node_id:
            raise ValueError("UI node id is required")
        children = [
            cls.from_dict(item)
            for item in value.get("children", [])
            if isinstance(item, dict)
        ]
        hints_value = (
            value.get("split_hints")
            or value.get("splitHints")
            or value.get("decomposition_hints")
            or value.get("decompositionHints")
            or []
        )
        split_hints = [
            cls.from_dict(item)
            for item in hints_value
            if isinstance(item, dict)
        ]
        return cls(
            id=node_id,
            purpose=str(value.get("purpose") or "").strip(),
            density=str(value.get("density") or "comfortable").strip() or "comfortable",
            primary_perceptual_task=str(
                _camel_or_snake(value, "primary_perceptual_task", "primaryPerceptualTask", "")
                or ""
            ).strip(),
            importance=str(value.get("importance") or value.get("candidateKind") or "secondaryRegion"),
            complexity=ComplexitySignals.from_dict(value),
            layout_envelope=LayoutEnvelope.from_dict(
                _camel_or_snake(value, "layout_envelope", "layoutEnvelope")
            ),
            inputs=_string_list(value.get("inputs")),
            events=_string_list(value.get("events")),
            required_states=_string_list(
                _camel_or_snake(value, "required_states", "requiredStates")
            ),
            allowed_primitives=_string_list(
                _camel_or_snake(value, "allowed_primitives", "allowedPrimitives")
            ),
            visible_action_budget=_positive_int(
                _camel_or_snake(value, "visible_action_budget", "visibleActionBudget", 3),
                3,
            ),
            children=children,
            split_hints=split_hints,
            metadata=dict(value.get("metadata") or {}),
        )

    def with_children(self, children: list["UINode"]) -> "UINode":
        return UINode(
            id=self.id,
            purpose=self.purpose,
            density=self.density,
            primary_perceptual_task=self.primary_perceptual_task,
            importance=self.importance,
            complexity=self.complexity,
            layout_envelope=self.layout_envelope,
            inputs=list(self.inputs),
            events=list(self.events),
            required_states=list(self.required_states),
            allowed_primitives=list(self.allowed_primitives),
            visible_action_budget=self.visible_action_budget,
            children=children,
            split_hints=list(self.split_hints),
            metadata=dict(self.metadata),
        )

    def to_dict(self, *, include_split_hints: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "purpose": self.purpose,
            "density": self.density,
            "primaryPerceptualTask": self.primary_perceptual_task,
            "importance": self.importance,
            "complexity": self.complexity.to_dict(),
            "layoutEnvelope": self.layout_envelope.to_dict(),
            "inputs": list(self.inputs),
            "events": list(self.events),
            "requiredStates": list(self.required_states),
            "allowedPrimitives": list(self.allowed_primitives),
            "visibleActionBudget": self.visible_action_budget,
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
    layout_envelope: LayoutEnvelope
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
            layout_envelope=node.layout_envelope,
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
            "id": self.id,
            "purpose": self.purpose,
            "primaryPerceptualTask": self.primary_perceptual_task,
            "density": self.density,
            "layoutEnvelope": self.layout_envelope.to_dict(),
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

    def contracts(self) -> list[ComponentContract]:
        return [leaf.contract for leaf in self.leaves() if leaf.contract is not None]

    def over_budget_leaves(self) -> list["PlannedNode"]:
        return [leaf for leaf in self.leaves() if leaf.budget_violations]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node.id,
            "purpose": self.node.purpose,
            "density": self.node.density,
            "importance": self.node.importance,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "createdAt": self.created_at,
            "config": self.config.to_dict(),
            "root": self.root.to_dict(),
            "contracts": [contract.to_dict() for contract in self.contracts()],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "summary": {
                "leafCount": len(self.root.leaves()),
                "contractCount": len(self.contracts()),
                "overBudgetLeafCount": len(self.over_budget_leaves()),
            },
        }
