from __future__ import annotations

import math
import uuid
from typing import Any

from .complexity import budget_violations, calculate_complexity
from .models import (
    ComponentContract,
    ComplexitySignals,
    LeafBudget,
    PlannedNode,
    PlanningDiagnostic,
    UICompilerConfig,
    UINode,
    UIPlan,
)


_HEURISTIC_SPLIT_LABELS = [
    ("overview", "overview and primary reading path"),
    ("primary-workspace", "primary work area"),
    ("interaction-region", "bounded interactive controls"),
    ("state-feedback", "state and recovery feedback"),
    ("responsive-adapter", "responsive layout adaptation"),
    ("supporting-context", "supporting context"),
    ("overflow-region", "overflow and long-content handling"),
    ("confirmation-flow", "confirmation and completion flow"),
]


class RecursiveUIPlanner:
    def __init__(self, config: UICompilerConfig | dict[str, Any] | None = None) -> None:
        self.config = (
            config
            if isinstance(config, UICompilerConfig)
            else UICompilerConfig.from_dict(config or {})
        )
        self._diagnostics: list[PlanningDiagnostic] = []

    def plan(self, root: UINode | dict[str, Any], *, run_id: str | None = None) -> UIPlan:
        self._diagnostics = []
        node = root if isinstance(root, UINode) else UINode.from_dict(root)
        planned_root = self._plan_node(node, depth=0)
        return UIPlan(
            run_id=run_id or f"ui_{uuid.uuid4().hex[:12]}",
            root=planned_root,
            config=self.config,
            diagnostics=list(self._diagnostics),
        )

    def _plan_node(self, node: UINode, *, depth: int) -> PlannedNode:
        score = calculate_complexity(node)
        violations = budget_violations(node, self.config.leaf_budget)

        if node.children:
            children = [self._plan_node(child, depth=depth + 1) for child in node.children]
            return PlannedNode(
                node=node,
                complexity_score=score,
                budget_violations=[],
                split_reason="explicit-children",
                children=children,
                contract=None,
            )

        if not violations:
            return PlannedNode(
                node=node,
                complexity_score=score,
                budget_violations=[],
                children=[],
                contract=self._contract_for_leaf(node, score),
            )

        split_children = self._split_node(node, violations=violations, depth=depth)
        if not split_children:
            self._diagnostics.append(
                PlanningDiagnostic(
                    code="oversized_leaf_without_split",
                    message="Leaf exceeds the recursive UI compiler budget and could not be split.",
                    node_id=node.id,
                    severity="error",
                    details={"violations": violations, "complexityScore": score},
                )
            )
            return PlannedNode(
                node=node,
                complexity_score=score,
                budget_violations=violations,
                children=[],
                contract=self._contract_for_leaf(node, score),
            )

        for child in split_children:
            self._maybe_warn_about_tiny_split(node, child)

        planned_children = [self._plan_node(child, depth=depth + 1) for child in split_children]
        return PlannedNode(
            node=node.with_children(split_children),
            complexity_score=score,
            budget_violations=[],
            split_reason="budget:" + ",".join(violations),
            children=planned_children,
            contract=None,
        )

    def _contract_for_leaf(self, node: UINode, score: float) -> ComponentContract:
        return ComponentContract.from_node(
            node,
            complexity_score=score,
            candidate_count=self.config.candidates.for_importance(node.importance),
        )

    def _split_node(self, node: UINode, *, violations: list[str], depth: int) -> list[UINode]:
        del violations
        if depth > 8:
            return []
        if node.split_hints:
            return list(node.split_hints)
        return self._heuristic_split(node)

    def _heuristic_split(self, node: UINode) -> list[UINode]:
        budget = self.config.leaf_budget
        signals = node.complexity
        count = self._required_split_count(signals, budget)
        if count < 2:
            return []

        role_parts = _distribute(signals.unique_visual_roles, count)
        control_parts = _distribute(signals.interactive_controls, count)
        state_parts = _distribute(signals.meaningful_states, count)
        mutation_parts = _distribute(signals.async_mutations, count)
        topology_parts = _distribute(signals.responsive_topologies, count, minimum=1)
        layout_parts = _distribute(signals.special_layout_algorithms, count)
        inputs_parts = _chunk_list(node.inputs, count)
        events_parts = _chunk_list(node.events, count)
        state_name_parts = _chunk_list(node.required_states, count)

        children: list[UINode] = []
        for index in range(count):
            label, purpose_suffix = _HEURISTIC_SPLIT_LABELS[index % len(_HEURISTIC_SPLIT_LABELS)]
            child_id = f"{node.id}-{label}"
            child_purpose = node.purpose
            if child_purpose:
                child_purpose = f"{child_purpose}: {purpose_suffix}"
            else:
                child_purpose = purpose_suffix
            child_metadata = dict(node.metadata)
            child_metadata["generatedBy"] = "recursive-ui-planner"
            child_metadata["parentNodeId"] = node.id
            children.append(
                UINode(
                    id=child_id,
                    purpose=child_purpose,
                    density=node.density,
                    primary_perceptual_task=node.primary_perceptual_task or node.purpose,
                    importance=node.importance,
                    complexity=ComplexitySignals(
                        unique_visual_roles=role_parts[index],
                        interactive_controls=control_parts[index],
                        meaningful_states=state_parts[index],
                        async_mutations=mutation_parts[index],
                        responsive_topologies=topology_parts[index],
                        special_layout_algorithms=layout_parts[index],
                    ),
                    layout_envelope=node.layout_envelope,
                    inputs=inputs_parts[index],
                    events=events_parts[index],
                    required_states=state_name_parts[index],
                    allowed_primitives=list(node.allowed_primitives),
                    visible_action_budget=max(1, min(node.visible_action_budget, budget.max_interactive_controls)),
                    children=[],
                    split_hints=[],
                    metadata=child_metadata,
                )
            )
        return children

    def _required_split_count(self, signals: ComplexitySignals, budget: LeafBudget) -> int:
        score = calculate_complexity(signals)
        counts = [
            math.ceil(score / budget.max_complexity) if budget.max_complexity else 1,
            math.ceil(signals.unique_visual_roles / budget.max_visual_roles),
            math.ceil(signals.interactive_controls / budget.max_interactive_controls),
            math.ceil(signals.async_mutations / budget.max_mutations),
            math.ceil(signals.responsive_topologies / budget.max_responsive_topologies),
            math.ceil(signals.special_layout_algorithms / budget.max_special_layout_algorithms),
        ]
        required = max(2, *(count for count in counts if count > 0))
        return min(required, 12)

    def _maybe_warn_about_tiny_split(self, parent: UINode, child: UINode) -> None:
        child_score = calculate_complexity(child)
        if (
            child.complexity.unique_visual_roles < self.config.leaf_budget.min_visual_roles
            and child.complexity.interactive_controls == 0
            and child_score < 8
        ):
            self._diagnostics.append(
                PlanningDiagnostic(
                    code="tiny_split_leaf",
                    message="Split leaf may be too small for a useful component cluster.",
                    node_id=child.id,
                    severity="warning",
                    details={"parentNodeId": parent.id, "complexityScore": child_score},
                )
            )


def _distribute(total: int, count: int, *, minimum: int = 0) -> list[int]:
    if count <= 0:
        return []
    if total <= 0:
        return [minimum for _ in range(count)]
    base, remainder = divmod(total, count)
    result = [base + (1 if index < remainder else 0) for index in range(count)]
    if minimum:
        result = [max(minimum, item) for item in result]
    return result


def _chunk_list(items: list[str], count: int) -> list[list[str]]:
    if count <= 0:
        return []
    chunks: list[list[str]] = [[] for _ in range(count)]
    for index, item in enumerate(items):
        chunks[index % count].append(item)
    return chunks
