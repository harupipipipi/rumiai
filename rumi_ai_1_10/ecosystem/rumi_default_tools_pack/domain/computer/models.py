"""Data models for the ComputerSeat architecture.

These dataclasses represent targets, capabilities, observation results,
action results, and accessibility tree elements used throughout the
driver chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComputerTarget:
    """Identifies the target application/window for an action."""

    app: str | None = None
    pid: int | None = None
    window_id: int | None = None
    window_title: str | None = None


@dataclass
class ComputerCapabilities:
    """Declares what a driver can do."""

    can_capture_background_window: bool = False
    can_semantic_action: bool = False
    can_pid_event: bool = False
    can_foreground_action: bool = True
    can_parallel_user_work: bool = False


@dataclass
class AXElement:
    """Represents a single element in the accessibility tree."""

    id: str = ""
    role: str = ""
    title: str = ""
    description: str = ""
    value: Any = None
    enabled: bool = True
    frame: dict[str, float] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)


@dataclass
class ObserveResult:
    """Result of an observe operation – screenshot + AX tree + metadata."""

    platform: str = ""
    target_window: dict[str, Any] = field(default_factory=dict)
    screenshot: dict[str, Any] = field(default_factory=dict)
    ax_tree: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, bool] = field(default_factory=dict)
    recommended_next_actions: list[dict[str, Any]] = field(default_factory=list)
    fallback_available: bool = True


@dataclass
class ActionResult:
    """Result of executing an action through a driver."""

    action: str = ""
    driver: str = ""
    executed: bool = False
    confidence: str = "best_effort"
    is_fallback: bool = False
    can_parallel_user_work: bool = False
    notes: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
