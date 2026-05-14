"""MacAccessibilityDriver – AX tree operations.

Uses the macOS Accessibility API to observe and interact with applications.
This is the highest-priority Mac driver because it can perform semantic
actions without requiring foreground activation.
"""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class MacAccessibilityDriver(ComputerDriver):
    """Driver using macOS Accessibility API (AX) for semantic interaction.

    Supports reading the AX tree, pressing buttons, setting values, and
    other semantic actions without needing the window in the foreground.
    Requires Accessibility permission (TCC).
    """

    @property
    def name(self) -> str:
        return "mac_accessibility"

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=False,
            can_semantic_action=True,
            can_pid_event=False,
            can_foreground_action=False,
            can_parallel_user_work=True,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        """Read the AX tree for the target application.

        Args:
            target: The target to observe.

        Returns:
            ObserveResult with ax_tree data.
        """
        from ..mac.ax import ax_get_tree

        try:
            tree = ax_get_tree(
                pid=target.pid,
                app=target.app,
                window_title=target.window_title,
                window_id=target.window_id,
            )
            return ObserveResult(
                platform="darwin",
                target_window={"app": target.app, "pid": target.pid},
                ax_tree=tree,
                capabilities={
                    "can_semantic_action": True,
                    "can_parallel_user_work": True,
                },
                fallback_available=True,
            )
        except Exception as e:
            return ObserveResult(
                platform="darwin",
                target_window={"app": target.app, "pid": target.pid},
                ax_tree={"error": str(e)},
                fallback_available=True,
            )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        """Click via AX – find element at point and perform AXPress.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            button: Mouse button (only left supported via AX).

        Returns:
            ActionResult.
        """
        from ..mac.ax import ax_find_candidates, ax_press

        try:
            if button != "left":
                return ActionResult(
                    action="click",
                    driver=self.name,
                    executed=False,
                    notes=["AXPress only supports primary-button semantic clicks"],
                )

            candidates = ax_find_candidates(
                pid=target.pid,
                app=target.app,
                point=(x, y),
                window_title=target.window_title,
                window_id=target.window_id,
            )
            if not candidates:
                return ActionResult(
                    action="click",
                    driver=self.name,
                    executed=False,
                    notes=[f"No AX element found at ({x}, {y})"],
                )

            element = candidates[0]
            success = ax_press(element_id=element.get("id", ""))
            return ActionResult(
                action="click",
                driver=self.name,
                executed=success,
                confidence="high" if success else "failed",
                can_parallel_user_work=True,
                data={"element": element},
            )
        except Exception as e:
            return ActionResult(
                action="click",
                driver=self.name,
                executed=False,
                notes=[f"AX click failed: {e}"],
            )

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        """Type text via AXSetValue on the focused element.

        Args:
            target: The target application/window.
            text: The text to set.

        Returns:
            ActionResult.
        """
        from ..mac.ax import ax_set_value

        try:
            success = ax_set_value(pid=target.pid, app=target.app, value=text)
            return ActionResult(
                action="type_text",
                driver=self.name,
                executed=success,
                confidence="high" if success else "failed",
                can_parallel_user_work=True,
            )
        except Exception as e:
            return ActionResult(
                action="type_text",
                driver=self.name,
                executed=False,
                notes=[f"AXSetValue failed: {e}"],
            )

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        """Key combos are not directly supported via AX API.

        Falls through to the next driver in the chain.

        Args:
            target: The target application/window.
            key_combo: Key combination string.

        Returns:
            ActionResult with executed=False.
        """
        return ActionResult(
            action="key",
            driver=self.name,
            executed=False,
            notes=["AX API does not support key combos directly; use CGEvent"],
        )

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        """Scroll is not directly supported via AX API.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            direction: Scroll direction.
            clicks: Number of scroll clicks.

        Returns:
            ActionResult with executed=False.
        """
        return ActionResult(
            action="scroll",
            driver=self.name,
            executed=False,
            notes=["AX API does not support scroll directly; use CGEvent"],
        )

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        """Execute a semantic action via AX (e.g. press a button by role/title).

        Args:
            target: The target application/window.
            intent: Natural language intent.
            element_or_point: AX element dict or (x, y) tuple.

        Returns:
            ActionResult.
        """
        from ..mac.ax import ax_find_candidates, ax_press

        try:
            # If element_or_point is a dict with an id, press it directly
            if isinstance(element_or_point, dict) and "id" in element_or_point:
                success = ax_press(element_id=element_or_point["id"])
                return ActionResult(
                    action="semantic_action",
                    driver=self.name,
                    executed=success,
                    confidence="high" if success else "failed",
                    can_parallel_user_work=True,
                    data={"element": element_or_point, "intent": intent},
                )

            point = None
            if (
                isinstance(element_or_point, (tuple, list))
                and len(element_or_point) >= 2
            ):
                point = (int(element_or_point[0]), int(element_or_point[1]))

            # Otherwise try to find candidates matching the intent
            candidates = ax_find_candidates(
                pid=target.pid,
                app=target.app,
                intent=intent,
                point=point,
                window_title=target.window_title,
                window_id=target.window_id,
            )
            if not candidates:
                return ActionResult(
                    action="semantic_action",
                    driver=self.name,
                    executed=False,
                    notes=[f"No AX element found for intent: {intent}"],
                )

            element = candidates[0]
            success = ax_press(element_id=element.get("id", ""))
            return ActionResult(
                action="semantic_action",
                driver=self.name,
                executed=success,
                confidence="high" if success else "medium",
                can_parallel_user_work=True,
                data={"element": element, "intent": intent},
            )
        except Exception as e:
            return ActionResult(
                action="semantic_action",
                driver=self.name,
                executed=False,
                notes=[f"AX semantic action failed: {e}"],
            )

    def is_available(self) -> bool:
        """Available on macOS when Accessibility permission is granted."""
        if sys.platform != "darwin":
            return False
        from ..mac.ax import ax_is_trusted

        return ax_is_trusted()
