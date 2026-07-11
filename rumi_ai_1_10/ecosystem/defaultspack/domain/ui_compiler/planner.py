from __future__ import annotations

import uuid
from typing import Any

from .complexity import budget_violations, calculate_complexity
from .models import (
    ComponentContract,
    PlannedNode,
    PlanningDiagnostic,
    UICompilerConfig,
    UINode,
    UIPlan,
)


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
        try:
            node = (
                root
                if isinstance(root, UINode)
                else UINode.from_dict(root, limits=self.config.resource_limits)
            )
        except ValueError as exc:
            diagnostics = [
                PlanningDiagnostic(
                    code="INVALID_UI_TREE",
                    message=str(exc),
                    node_id="",
                    severity="error",
                )
            ]
            empty = UINode.from_dict({"id": "invalid-plan"}, limits=self.config.resource_limits)
            return UIPlan(
                run_id=run_id or f"ui-{uuid.uuid4().hex[:12]}",
                root=PlannedNode(node=empty, complexity_score=0.0),
                config=self.config,
                diagnostics=diagnostics,
            )

        self._validate_unique_ids(node)
        planned_root = self._plan_node(node, depth=0)
        plan = UIPlan(
            run_id=run_id or f"ui-{uuid.uuid4().hex[:12]}",
            root=planned_root,
            config=self.config,
            diagnostics=list(self._diagnostics),
        )
        if len(plan.root.planned_nodes()) > self.config.resource_limits.max_generated_nodes:
            self._diagnostics.append(
                PlanningDiagnostic(
                    code="PLAN_NODE_LIMIT_EXCEEDED",
                    message="Plan exceeds max generated nodes.",
                    node_id=node.id,
                    severity="error",
                    details={"maxGeneratedNodes": self.config.resource_limits.max_generated_nodes},
                )
            )
            plan = UIPlan(
                run_id=plan.run_id,
                root=planned_root,
                config=self.config,
                diagnostics=list(self._diagnostics),
                created_at=plan.created_at,
            )
        return plan

    def _plan_node(self, node: UINode, *, depth: int) -> PlannedNode:
        score = calculate_complexity(node)
        violations = budget_violations(node, self.config.leaf_budget)

        if depth > self.config.resource_limits.max_plan_depth:
            self._diagnostics.append(
                PlanningDiagnostic(
                    code="PLAN_DEPTH_LIMIT_EXCEEDED",
                    message="Plan exceeds max plan depth.",
                    node_id=node.id,
                    severity="error",
                    details={"maxPlanDepth": self.config.resource_limits.max_plan_depth},
                )
            )
            return PlannedNode(node=node, complexity_score=score, budget_violations=violations)

        if node.children:
            self._validate_parent_decomposition(node, node.children, split_kind="children")
            self._validate_slot_assignments(node, node.children, split_kind="children")
            children = [self._plan_node(child, depth=depth + 1) for child in node.children]
            return PlannedNode(
                node=node,
                complexity_score=score,
                budget_violations=[],
                split_reason="explicit-children",
                children=children,
                contract=self._contract_for_node(node, score)
                if self._node_has_contract(node, has_children=True)
                else None,
            )

        if violations:
            if node.split_hints:
                self._validate_parent_decomposition(node, node.split_hints, split_kind="splitHints")
                self._validate_slot_assignments(node, node.split_hints, split_kind="splitHints")
                children = [self._plan_node(child, depth=depth + 1) for child in node.split_hints]
                return PlannedNode(
                    node=node,
                    complexity_score=score,
                    budget_violations=[],
                    split_reason="semantic-split-hints",
                    children=children,
                    contract=self._contract_for_node(node, score)
                    if self._node_has_contract(node, has_children=True)
                    else None,
                )
            self._diagnostics.append(
                PlanningDiagnostic(
                    code="REQUIRES_SEMANTIC_DECOMPOSITION",
                    message=(
                        "Leaf exceeds the recursive UI compiler budget and requires an explicit "
                        "semantic split; heuristic executable splits are disabled."
                    ),
                    node_id=node.id,
                    severity="error",
                    details={
                        "violations": violations,
                        "complexityScore": score,
                        "suggestedRegions": [
                            "primary-workspace",
                            "interaction-region",
                            "state-feedback",
                        ],
                        "executable": False,
                    },
                )
            )
            return PlannedNode(
                node=node,
                complexity_score=score,
                budget_violations=violations,
                children=[],
                contract=None,
            )

        self._validate_slot_assignments(node, [], split_kind="leaf")
        contract = (
            self._contract_for_node(node, score)
            if self._node_has_contract(node, has_children=False)
            else None
        )
        if contract is None:
            self._diagnostics.append(
                PlanningDiagnostic(
                    code="UNIMPLEMENTED_LEAF_NODE",
                    message="Leaf nodes must produce an executable component contract.",
                    node_id=node.id,
                    severity="error",
                    details={
                        "implementationMode": node.implementation_mode,
                        "allowedLeafModes": [
                            "component",
                            "component-with-slots",
                            "repeated-component",
                        ],
                    },
                )
            )
        return PlannedNode(
            node=node,
            complexity_score=score,
            budget_violations=[],
            children=[],
            contract=contract,
        )

    def _contract_for_node(self, node: UINode, score: float) -> ComponentContract:
        return ComponentContract.from_node(
            node,
            complexity_score=score,
            candidate_count=self.config.candidates.for_importance(node.importance),
        )

    @staticmethod
    def _node_has_contract(node: UINode, *, has_children: bool) -> bool:
        if has_children:
            return node.implementation_mode == "component-with-slots"
        return node.implementation_mode in {"component", "component-with-slots", "repeated-component"}

    def _validate_unique_ids(self, node: UINode) -> None:
        seen: dict[str, str] = {}

        def visit(current: UINode) -> None:
            folded = current.id.casefold()
            previous = seen.get(folded)
            if previous is not None:
                self._diagnostics.append(
                    PlanningDiagnostic(
                        code="INVALID_NODE_ID",
                        message="UI node IDs must be globally unique, including case-folded IDs.",
                        node_id=current.id,
                        severity="error",
                        details={"firstNodeId": previous, "duplicateNodeId": current.id},
                    )
                )
            else:
                seen[folded] = current.id
            for child in [*current.children, *current.split_hints]:
                visit(child)

        visit(node)

    def _validate_parent_decomposition(
        self,
        parent: UINode,
        children: list[UINode],
        *,
        split_kind: str,
    ) -> None:
        if _has_unidentified_parent_complexity(parent):
            self._diagnostics.append(
                PlanningDiagnostic(
                    code="REQUIRES_RESPONSIBILITY_IDS",
                    message="Parent node has responsibilities or complexity that must be named before splitting.",
                    node_id=parent.id,
                    severity="error",
                    details={"splitKind": split_kind},
                )
            )
            return

        missing_evidence = _missing_complexity_evidence(parent)
        if missing_evidence:
            self._diagnostics.append(
                PlanningDiagnostic(
                    code="REQUIRES_RESPONSIBILITY_IDS",
                    message="Parent complexity must be backed by named responsibility IDs before splitting.",
                    node_id=parent.id,
                    severity="error",
                    details={"splitKind": split_kind, "missingEvidence": missing_evidence},
                )
            )
            return

        if not parent.responsibilities.has_any():
            return

        parent_categories = parent.responsibilities.categories()
        child_index = _child_responsibility_index(children)
        for category, ids in parent_categories.items():
            shared = set(parent.responsibilities.shared)
            for responsibility_id in ids:
                owners = child_index.get((category, responsibility_id), [])
                if not owners:
                    if _parent_contract_can_own_responsibility(parent, category):
                        continue
                    self._diagnostics.append(
                        PlanningDiagnostic(
                            code="RESPONSIBILITY_COVERAGE_MISSING",
                            message="Split drops a parent responsibility.",
                            node_id=parent.id,
                            severity="error",
                            details={
                                "splitKind": split_kind,
                                "category": category,
                                "responsibilityId": responsibility_id,
                            },
                        )
                    )
                elif len(owners) > 1 and responsibility_id not in shared:
                    self._diagnostics.append(
                        PlanningDiagnostic(
                            code="RESPONSIBILITY_COVERAGE_DUPLICATE",
                            message="Split assigns a parent responsibility to multiple children without shared ownership.",
                            node_id=parent.id,
                            severity="error",
                            details={
                                "splitKind": split_kind,
                                "category": category,
                                "responsibilityId": responsibility_id,
                                "owners": owners,
                            },
                        )
                    )

        self._validate_ownership_groups(parent, children, child_index)
        self._validate_input_event_pairs(parent, child_index)

    def _validate_ownership_groups(
        self,
        parent: UINode,
        children: list[UINode],
        child_index: dict[tuple[str, str], list[str]],
    ) -> None:
        del children
        for group in parent.ownership:
            owners: set[str] = set()
            for control_id in group.controls:
                owners.update(child_index.get(("controls", control_id), []))
            for mutation_id in group.mutations:
                owners.update(child_index.get(("mutations", mutation_id), []))
            for state_id in group.states:
                owners.update(child_index.get(("states", state_id), []))
            if len(owners) > 1:
                self._diagnostics.append(
                    PlanningDiagnostic(
                        code="OWNERSHIP_BOUNDARY_SPLIT",
                        message="Input/event, mutation, and state ownership must stay in one child boundary.",
                        node_id=parent.id,
                        severity="error",
                        details={"ownershipGroupId": group.id, "owners": sorted(owners)},
                    )
                )

    def _validate_input_event_pairs(
        self,
        parent: UINode,
        child_index: dict[tuple[str, str], list[str]],
    ) -> None:
        for input_id in parent.inputs:
            input_key = _semantic_key(input_id)
            for event_id in parent.events:
                if input_key != _semantic_key(event_id):
                    continue
                input_owners = set(child_index.get(("controls", input_id), []))
                event_owners = set(child_index.get(("controls", event_id), []))
                if input_owners and event_owners and input_owners != event_owners:
                    self._diagnostics.append(
                        PlanningDiagnostic(
                            code="OWNERSHIP_BOUNDARY_SPLIT",
                            message="Input and corresponding event must be owned by the same child.",
                            node_id=parent.id,
                            severity="error",
                            details={
                                "inputId": input_id,
                                "eventId": event_id,
                                "inputOwners": sorted(input_owners),
                                "eventOwners": sorted(event_owners),
                            },
                        )
                    )

    def _validate_slot_assignments(
        self,
        parent: UINode,
        children: list[UINode],
        *,
        split_kind: str,
    ) -> None:
        if not parent.slots:
            return

        child_ids = {child.id for child in children}
        assignments_by_child: dict[str, list[str]] = {}
        seen_slots: set[str] = set()
        for slot in parent.slots:
            folded = slot.id.casefold()
            if folded in seen_slots:
                self._diagnostics.append(
                    PlanningDiagnostic(
                        code="DUPLICATE_SLOT_ID",
                        message="Slot IDs must be unique within a node.",
                        node_id=parent.id,
                        severity="error",
                        details={"slotId": slot.id, "splitKind": split_kind},
                    )
                )
            seen_slots.add(folded)

            if slot.accepts_node_id is None:
                if slot.required:
                    self._diagnostics.append(
                        PlanningDiagnostic(
                            code="REQUIRED_SLOT_UNASSIGNED",
                            message="Required slots must declare the child node they accept.",
                            node_id=parent.id,
                            severity="error",
                            details={"slotId": slot.id, "splitKind": split_kind},
                        )
                    )
                continue
            if slot.accepts_node_id not in child_ids:
                self._diagnostics.append(
                    PlanningDiagnostic(
                        code="SLOT_ACCEPTS_UNKNOWN_CHILD",
                        message="Slot acceptsNodeId must reference one of the node's children.",
                        node_id=parent.id,
                        severity="error",
                        details={
                            "slotId": slot.id,
                            "acceptsNodeId": slot.accepts_node_id,
                            "splitKind": split_kind,
                        },
                    )
                )
                continue
            assignments_by_child.setdefault(slot.accepts_node_id, []).append(slot.id)

        for child in children:
            assigned_slots = assignments_by_child.get(child.id, [])
            if not assigned_slots:
                self._diagnostics.append(
                    PlanningDiagnostic(
                        code="CHILD_SLOT_ASSIGNMENT_MISSING",
                        message="Every child of a slotted component must be assigned to a slot.",
                        node_id=parent.id,
                        severity="error",
                        details={"childNodeId": child.id, "splitKind": split_kind},
                    )
                )
            elif len(assigned_slots) > 1:
                self._diagnostics.append(
                    PlanningDiagnostic(
                        code="CHILD_SLOT_ASSIGNMENT_DUPLICATE",
                        message="A child node cannot be assigned to multiple slots.",
                        node_id=parent.id,
                        severity="error",
                        details={
                            "childNodeId": child.id,
                            "slotIds": sorted(assigned_slots),
                            "splitKind": split_kind,
                        },
                    )
                )


def _has_unidentified_parent_complexity(parent: UINode) -> bool:
    if parent.responsibilities.has_any():
        return False
    return (
        parent.complexity.unique_visual_roles > 0
        or parent.complexity.interactive_controls > 0
        or parent.complexity.meaningful_states > 0
        or parent.complexity.async_mutations > 0
        or parent.complexity.responsive_topologies > 0
        or parent.complexity.special_layout_algorithms > 0
    )


def _missing_complexity_evidence(parent: UINode) -> dict[str, dict[str, int]]:
    checks = {
        "visualRoles": (
            parent.complexity.unique_visual_roles,
            len(parent.responsibilities.visual_roles),
        ),
        "controls": (
            parent.complexity.interactive_controls,
            len(parent.responsibilities.controls),
        ),
        "mutations": (
            parent.complexity.async_mutations,
            len(parent.responsibilities.mutations),
        ),
        "states": (
            parent.complexity.meaningful_states,
            len(parent.responsibilities.states),
        ),
        "layoutAlgorithms": (
            parent.complexity.special_layout_algorithms,
            len(parent.responsibilities.layout_algorithms),
        ),
        "responsiveTopologies": (
            parent.complexity.responsive_topologies,
            len(parent.responsibilities.responsive_topologies),
        ),
    }
    missing: dict[str, dict[str, int]] = {}
    for key, (claimed, evidenced) in checks.items():
        if claimed > evidenced:
            missing[key] = {"claimed": claimed, "evidenced": evidenced}
    return missing


def _child_responsibility_index(children: list[UINode]) -> dict[tuple[str, str], list[str]]:
    index: dict[tuple[str, str], list[str]] = {}
    for child in children:
        categories = child.responsibilities.categories()
        for category, ids in categories.items():
            for responsibility_id in ids:
                index.setdefault((category, responsibility_id), []).append(child.id)
    return index


def _parent_contract_can_own_responsibility(parent: UINode, category: str) -> bool:
    return (
        category in {"layoutAlgorithms", "responsiveTopologies"}
        and parent.implementation_mode == "component-with-slots"
    )


def _semantic_key(value: str) -> str:
    lowered = str(value or "").strip().lower()
    if lowered.startswith("on") and len(lowered) > 2:
        lowered = lowered[2:]
    for suffix in ("change", "changed", "select", "selected"):
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            lowered = lowered[: -len(suffix)]
    return lowered.strip("-_s")
