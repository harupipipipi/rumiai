"""MacAppleEventsDriver – safe allowlisted Apple Events actions.

Uses AppleScript / Apple Events to perform actions on applications that
support scriptable interfaces. Only allowlisted actions are permitted
to prevent unintended side effects.
"""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class MacAppleEventsDriver(ComputerDriver):
    """Driver using Apple Events for safe, allowlisted app interactions.

    Supports actions like:
    - Opening URLs in browsers
    - Switching tabs
    - Getting document content
    - Menu item activation (for allowlisted apps)
    """

    @property
    def name(self) -> str:
        return "mac_apple_events"

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=False,
            can_semantic_action=True,
            can_background_type=False,
            can_background_key=False,
            can_pid_event=False,
            can_foreground_action=False,
            can_parallel_user_work=False,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        """Observe via Apple Events (get window list, document info, etc.).

        Args:
            target: The target to observe.

        Returns:
            ObserveResult with Apple Events data.
        """
        from ..mac.applescript import get_app_info

        try:
            info = get_app_info(app=target.app or "")
            return ObserveResult(
                platform="darwin",
                target_window={"app": target.app, "pid": target.pid},
                ax_tree=info,
                capabilities={"can_semantic_action": True},
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
        """Click is not supported via Apple Events.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            button: Mouse button.

        Returns:
            ActionResult with executed=False.
        """
        return ActionResult(
            action="click",
            driver=self.name,
            executed=False,
            notes=["Apple Events does not support coordinate-based clicks"],
        )

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        """Type text via Apple Events keystroke command.

        Args:
            target: The target application/window.
            text: The text to type.

        Returns:
            ActionResult.
        """
        from ..mac.applescript import send_keystroke

        try:
            success = send_keystroke(app=target.app or "", text=text)
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
                notes=[f"Apple Events type failed: {e}"],
            )

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        """Send key combo via Apple Events.

        Args:
            target: The target application/window.
            key_combo: Key combination string.

        Returns:
            ActionResult.
        """
        from ..mac.applescript import send_key_combo

        try:
            success = send_key_combo(app=target.app or "", key_combo=key_combo)
            return ActionResult(
                action="key",
                driver=self.name,
                executed=success,
                confidence="high" if success else "failed",
                can_parallel_user_work=True,
            )
        except Exception as e:
            return ActionResult(
                action="key",
                driver=self.name,
                executed=False,
                notes=[f"Apple Events key failed: {e}"],
            )

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        """Scroll is not supported via Apple Events.

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
            notes=["Apple Events does not support scroll"],
        )

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        """Execute a semantic action via Apple Events.

        Supports allowlisted actions like menu clicks, URL opening, etc.

        Args:
            target: The target application/window.
            intent: Natural language intent.
            element_or_point: Element or point.

        Returns:
            ActionResult.
        """
        from ..mac.applescript import execute_safe_action

        try:
            result = execute_safe_action(
                app=target.app or "",
                intent=intent,
                element=element_or_point,
            )
            return ActionResult(
                action="semantic_action",
                driver=self.name,
                executed=result.get("success", False),
                confidence="high" if result.get("success") else "failed",
                can_parallel_user_work=True,
                data=result,
            )
        except Exception as e:
            return ActionResult(
                action="semantic_action",
                driver=self.name,
                executed=False,
                notes=[f"Apple Events semantic action failed: {e}"],
            )

    def is_available(self) -> bool:
        """Available on macOS only."""
        return sys.platform == "darwin"
