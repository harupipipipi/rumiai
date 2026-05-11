"""LocalVisibleDesktopDriver – wraps existing foreground actions.

This driver provides basic foreground-only desktop interaction by
activating the target window, performing the action, and optionally
restoring the previous window. It wraps the existing physical action
infrastructure.
"""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class LocalVisibleDesktopDriver(ComputerDriver):
    """Driver that uses foreground activation for all actions.

    This is the simplest driver – it brings the target window to front,
    performs the action using physical input events, then optionally
    restores the previous foreground window.
    """

    @property
    def name(self) -> str:
        return "local_visible"

    @property
    def platform(self) -> str:
        return sys.platform

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=False,
            can_semantic_action=False,
            can_pid_event=False,
            can_foreground_action=True,
            can_parallel_user_work=False,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        """Observe by taking a screenshot of the visible desktop.

        Args:
            target: The target to observe.

        Returns:
            ObserveResult with screenshot data.
        """
        # TODO: Integrate with existing screenshot infrastructure
        return ObserveResult(
            platform=sys.platform,
            target_window={"app": target.app, "pid": target.pid},
            capabilities={
                "can_capture_background_window": False,
                "can_foreground_action": True,
            },
            fallback_available=False,
        )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        """Click using physical mouse events (foreground required).

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            button: Mouse button.

        Returns:
            ActionResult.
        """
        # TODO: Integrate with existing click infrastructure
        return ActionResult(
            action="click",
            driver=self.name,
            executed=False,
            confidence="best_effort",
            can_parallel_user_work=False,
            notes=["LocalVisibleDesktopDriver.click: not yet integrated"],
        )

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        """Type text using physical keyboard events (foreground required).

        Args:
            target: The target application/window.
            text: The text to type.

        Returns:
            ActionResult.
        """
        # TODO: Integrate with existing type infrastructure
        return ActionResult(
            action="type_text",
            driver=self.name,
            executed=False,
            confidence="best_effort",
            can_parallel_user_work=False,
            notes=["LocalVisibleDesktopDriver.type_text: not yet integrated"],
        )

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        """Send key combo using physical keyboard events.

        Args:
            target: The target application/window.
            key_combo: Key combination string.

        Returns:
            ActionResult.
        """
        # TODO: Integrate with existing key infrastructure
        return ActionResult(
            action="key",
            driver=self.name,
            executed=False,
            confidence="best_effort",
            can_parallel_user_work=False,
            notes=["LocalVisibleDesktopDriver.key: not yet integrated"],
        )

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        """Scroll using physical scroll events.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            direction: Scroll direction.
            clicks: Number of scroll clicks.

        Returns:
            ActionResult.
        """
        # TODO: Integrate with existing scroll infrastructure
        return ActionResult(
            action="scroll",
            driver=self.name,
            executed=False,
            confidence="best_effort",
            can_parallel_user_work=False,
            notes=["LocalVisibleDesktopDriver.scroll: not yet integrated"],
        )

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        """Not supported – this driver has no semantic capabilities.

        Args:
            target: The target application/window.
            intent: Intent description.
            element_or_point: Element or point.

        Returns:
            ActionResult with executed=False.
        """
        return ActionResult(
            action="semantic_action",
            driver=self.name,
            executed=False,
            confidence="none",
            notes=["LocalVisibleDesktopDriver does not support semantic actions"],
        )

    def is_available(self) -> bool:
        """Always available as a last-resort driver."""
        return True
