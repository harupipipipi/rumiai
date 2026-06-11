from __future__ import annotations

from typing import Any

from .models import ContextSectionBudget, ContextValidationResult
from .token_estimator import estimate_tokens


DEFAULT_SECTION_BUDGETS: dict[str, ContextSectionBudget] = {
    "summary": ContextSectionBudget("summary", max_items=1, max_tokens=4000),
    "progress": ContextSectionBudget("progress", max_items=30, max_tokens=2000),
    "decisions": ContextSectionBudget("decisions", max_items=40, max_tokens=2500),
    "constraints": ContextSectionBudget("constraints", max_items=30, max_tokens=1500),
    "user_preferences": ContextSectionBudget("user_preferences", max_items=30, max_tokens=1500),
    "changed_files": ContextSectionBudget("changed_files", max_items=200, max_tokens=2500),
    "tool_results": ContextSectionBudget("tool_results", max_items=30, max_tokens=6000),
    "terminal_results": ContextSectionBudget("terminal_results", max_items=20, max_tokens=6000),
    "pinned_context": ContextSectionBudget("pinned_context", max_items=40, max_tokens=5000),
    "dropped_context_log": ContextSectionBudget("dropped_context_log", max_items=80, max_tokens=5000),
    "memory_flush_refs": ContextSectionBudget("memory_flush_refs", max_items=80, max_tokens=2500),
    "next_steps": ContextSectionBudget("next_steps", max_items=40, max_tokens=2500),
    "critical_context": ContextSectionBudget("critical_context", max_items=40, max_tokens=5000),
}

LIST_SECTIONS = {
    "decisions",
    "constraints",
    "user_preferences",
    "changed_files",
    "tool_results",
    "terminal_results",
    "pinned_context",
    "dropped_context_log",
    "memory_flush_refs",
    "next_steps",
    "critical_context",
}


def validate_compact_packet(packet: dict[str, Any]) -> ContextValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    sections: dict[str, dict[str, int]] = {}

    if not isinstance(packet, dict):
        return ContextValidationResult(valid=False, errors=["packet must be an object"])

    if not str(packet.get("compact_id") or "").strip():
        errors.append("compact_id is required")
    if "summary" not in packet:
        errors.append("summary is required")

    progress = packet.get("progress")
    if progress is not None and not isinstance(progress, dict):
        errors.append("progress must be an object")
    for section in LIST_SECTIONS:
        value = packet.get(section)
        if value is not None and not isinstance(value, list):
            errors.append(section + " must be a list")

    for section, budget in DEFAULT_SECTION_BUDGETS.items():
        value = packet.get(section)
        item_count = _item_count(value)
        token_count = estimate_tokens(value)
        sections[section] = {"items": item_count, "tokens": token_count}
        if budget.max_items and item_count > budget.max_items:
            warnings.append(
                f"{section} has {item_count} items; budget is {budget.max_items}"
            )
        if budget.max_tokens and token_count > budget.max_tokens:
            warnings.append(
                f"{section} uses {token_count} estimated tokens; budget is {budget.max_tokens}"
            )

    return ContextValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        sections=sections,
    )


def _item_count(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1
