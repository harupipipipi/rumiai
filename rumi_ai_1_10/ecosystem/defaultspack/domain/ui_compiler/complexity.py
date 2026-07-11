from __future__ import annotations

from typing import Any

from .models import ComplexitySignals, LeafBudget, UINode


def normalize_signals(value: Any) -> ComplexitySignals:
    if isinstance(value, ComplexitySignals):
        return value
    if isinstance(value, UINode):
        return value.complexity
    if isinstance(value, dict):
        return ComplexitySignals.from_dict(value)
    return ComplexitySignals()


def calculate_complexity(value: Any) -> float:
    signals = normalize_signals(value)
    return (
        signals.unique_visual_roles
        + signals.interactive_controls * 2
        + signals.meaningful_states * 1.5
        + signals.async_mutations * 5
        + signals.responsive_topologies * 4
        + signals.special_layout_algorithms * 6
    )


def budget_violations(value: Any, budget: LeafBudget | None = None) -> list[str]:
    leaf_budget = budget or LeafBudget()
    signals = normalize_signals(value)
    score = calculate_complexity(signals)
    violations: list[str] = []
    if score > leaf_budget.max_complexity:
        violations.append("complexity")
    if signals.unique_visual_roles > leaf_budget.max_visual_roles:
        violations.append("visual_roles")
    if signals.interactive_controls > leaf_budget.max_interactive_controls:
        violations.append("interactive_controls")
    if signals.async_mutations > leaf_budget.max_mutations:
        violations.append("async_mutations")
    if signals.responsive_topologies > leaf_budget.max_responsive_topologies:
        violations.append("responsive_topologies")
    if signals.special_layout_algorithms > leaf_budget.max_special_layout_algorithms:
        violations.append("special_layout_algorithms")
    return violations


def is_within_leaf_budget(value: Any, budget: LeafBudget | None = None) -> bool:
    return not budget_violations(value, budget)
