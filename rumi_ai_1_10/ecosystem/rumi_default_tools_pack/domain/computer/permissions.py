"""Permission and approval checking for ComputerSeat actions.

Actions are classified into risk levels. High-risk actions require explicit
user approval before execution.
"""

from __future__ import annotations

from typing import Literal

# Risk classification for action types
_RISK_MAP: dict[str, Literal["low", "medium", "high"]] = {
    # Low-risk: read-only / observation
    "observe": "low",
    "list": "low",
    "screenshot": "low",
    "ax_tree_read": "low",
    # Medium-risk: limited side effects
    "scroll": "medium",
    "move": "medium",
    # High-risk: mutations / input injection
    "ax_press": "high",
    "ax_set_value": "high",
    "type_text": "high",
    "key": "high",
    "click": "high",
    "drag": "high",
    "apple_events_mutation": "high",
    "post_to_pid": "high",
    "foreground_fallback": "high",
    "semantic_action": "high",
}


def risk_level(action: str) -> Literal["low", "medium", "high"]:
    """Return the risk level for a given action name.

    Args:
        action: The action identifier (e.g. "observe", "click", "type_text").

    Returns:
        One of "low", "medium", or "high".
    """
    return _RISK_MAP.get(action, "high")


def requires_approval(action: str) -> bool:
    """Check whether an action requires explicit user approval.

    Args:
        action: The action identifier.

    Returns:
        True if the action is high-risk and needs approval.
    """
    return risk_level(action) == "high"
