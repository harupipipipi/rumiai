"""MacCGEventPidDriver – experimental pid-targeted CGEvent injection.

Uses CGEventPostToPid to send keyboard and mouse events directly to a
specific process without requiring foreground activation.

⚠️ EXPERIMENTAL: CGEventPostToPid behavior varies by application and
macOS version. Some apps ignore pid-targeted events. This driver should
be used as a fallback when AX actions are not available.
"""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class MacCGEventPidDriver(ComputerDriver):
    """Experimental driver using CGEventPostToPid for background input.

    ⚠️ EXPERIMENTAL: Not all applications respond to pid-targeted events.
    """

    @property
    def name(self) -> str:
        return "mac_cgevent_pid"

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=False,
            can_semantic_action=False,
            can_background_click=True,
            can_background_type=True,
            can_background_key=True,
            can_background_scroll=True,
            can_pid_event=True,
            can_foreground_action=False,
            can_parallel_user_work=True,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        """CGEvent driver does not support observation.

        Args:
            target: The target to observe.

        Returns:
            Empty ObserveResult.
        """
        return ObserveResult(
            platform="darwin",
            target_window={"app": target.app, "pid": target.pid},
            capabilities={"can_pid_event": True},
            fallback_available=True,
        )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        """Click via CGEventPostToPid.

        ⚠️ EXPERIMENTAL: May not work with all applications.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            button: Mouse button.

        Returns:
            ActionResult.
        """
        from ..mac.cgevent import post_click_to_pid

        if target.pid is None:
            return ActionResult(
                action="click",
                driver=self.name,
                executed=False,
                notes=["CGEventPostToPid requires a PID"],
            )

        try:
            success = post_click_to_pid(pid=target.pid, x=x, y=y, button=button)
            return ActionResult(
                action="click",
                driver=self.name,
                executed=success,
                confidence="experimental",
                can_parallel_user_work=True,
                uses_physical_input=False,
                notes=["⚠️ EXPERIMENTAL: CGEventPostToPid click"],
            )
        except Exception as e:
            return ActionResult(
                action="click",
                driver=self.name,
                executed=False,
                notes=[f"CGEvent click failed: {e}"],
            )

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        """Type text via CGEventPostToPid key events.

        ⚠️ EXPERIMENTAL: May not work with all applications.

        Args:
            target: The target application/window.
            text: The text to type.

        Returns:
            ActionResult.
        """
        from ..mac.cgevent import post_key_to_pid

        if target.pid is None:
            return ActionResult(
                action="type_text",
                driver=self.name,
                executed=False,
                notes=["CGEventPostToPid requires a PID"],
            )

        try:
            success = post_key_to_pid(pid=target.pid, text=text)
            return ActionResult(
                action="type_text",
                driver=self.name,
                executed=success,
                confidence="experimental",
                can_parallel_user_work=True,
                uses_physical_input=False,
                notes=["⚠️ EXPERIMENTAL: CGEventPostToPid type"],
            )
        except Exception as e:
            return ActionResult(
                action="type_text",
                driver=self.name,
                executed=False,
                notes=[f"CGEvent type failed: {e}"],
            )

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        """Send key combo via CGEventPostToPid.

        ⚠️ EXPERIMENTAL: May not work with all applications.

        Args:
            target: The target application/window.
            key_combo: Key combination string.

        Returns:
            ActionResult.
        """
        from ..mac.cgevent import post_key_to_pid

        if target.pid is None:
            return ActionResult(
                action="key",
                driver=self.name,
                executed=False,
                notes=["CGEventPostToPid requires a PID"],
            )

        try:
            success = post_key_to_pid(pid=target.pid, key_combo=key_combo)
            return ActionResult(
                action="key",
                driver=self.name,
                executed=success,
                confidence="experimental",
                can_parallel_user_work=True,
                uses_physical_input=False,
                notes=["⚠️ EXPERIMENTAL: CGEventPostToPid key"],
            )
        except Exception as e:
            return ActionResult(
                action="key",
                driver=self.name,
                executed=False,
                notes=[f"CGEvent key failed: {e}"],
            )

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        """Scroll via CGEventPostToPid.

        ⚠️ EXPERIMENTAL: May not work with all applications.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            direction: Scroll direction.
            clicks: Number of scroll clicks.

        Returns:
            ActionResult.
        """
        from ..mac.cgevent import post_scroll_to_pid

        if target.pid is None:
            return ActionResult(
                action="scroll",
                driver=self.name,
                executed=False,
                notes=["CGEventPostToPid requires a PID"],
            )

        try:
            success = post_scroll_to_pid(pid=target.pid, x=x, y=y, direction=direction, clicks=clicks)
            return ActionResult(
                action="scroll",
                driver=self.name,
                executed=success,
                confidence="experimental",
                can_parallel_user_work=True,
                uses_physical_input=False,
                notes=["⚠️ EXPERIMENTAL: CGEventPostToPid scroll"],
            )
        except Exception as e:
            return ActionResult(
                action="scroll",
                driver=self.name,
                executed=False,
                notes=[f"CGEvent scroll failed: {e}"],
            )

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        """Not supported – CGEvent has no semantic capabilities.

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
            notes=["CGEvent driver does not support semantic actions"],
        )

    def is_available(self) -> bool:
        """Available on macOS only."""
        return sys.platform == "darwin"
