"""MacForegroundFallbackDriver – activate + physical action + restore.

Last-resort driver that brings the target window to the foreground,
performs the action using physical input events, then restores the
previously active window. This interrupts the user but guarantees
the action reaches the target.
"""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver
from . import foreground_io


class MacForegroundFallbackDriver(ComputerDriver):
    """Fallback driver that activates the target window for actions.

    This driver:
    1. Records the currently active window
    2. Activates the target application
    3. Performs the physical action
    4. Restores the previously active window

    ⚠️ This interrupts the user's workflow.
    """

    @property
    def name(self) -> str:
        return "mac_foreground"

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=False,
            can_semantic_action=False,
            can_pid_event=False,
            can_foreground_action=True,
            can_parallel_user_work=False,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        """Observe by activating the window and taking a screenshot.

        Args:
            target: The target to observe.

        Returns:
            ObserveResult.
        """
        from ..mac.helper import activate_app, get_frontmost_app, restore_app
        from ..mac.screencapture import capture_window

        previous_app = get_frontmost_app()
        try:
            if not activate_app(target.app or "", target.pid):
                return ObserveResult(
                    platform="darwin",
                    target_window={"app": target.app, "pid": target.pid},
                    screenshot={"method": "unavailable", "error": "Could not activate target application."},
                    capabilities={"can_foreground_action": True},
                    fallback_available=False,
                )
            screenshot_data = capture_window(
                window_id=target.window_id,
                pid=target.pid,
                app=target.app,
            )
            return ObserveResult(
                platform="darwin",
                target_window={"app": target.app, "pid": target.pid},
                screenshot=screenshot_data,
                capabilities={"can_foreground_action": True},
                fallback_available=False,
            )
        finally:
            if previous_app:
                restore_app(previous_app)

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        """Click via foreground activation + physical mouse event.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            button: Mouse button.

        Returns:
            ActionResult.
        """
        from ..mac.helper import activate_app, get_frontmost_app, restore_app

        previous_app = get_frontmost_app()
        try:
            if not activate_app(target.app or "", target.pid):
                return self._failure("click", target, "Could not activate target application.")
            foreground_io.click(int(x), int(y), button, platform_name="darwin")
            return self._success("click", target)
        except Exception as e:
            return self._failure("click", target, f"Foreground click failed: {e}")
        finally:
            if previous_app:
                restore_app(previous_app)

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        """Type text via foreground activation + physical keyboard events.

        Args:
            target: The target application/window.
            text: The text to type.

        Returns:
            ActionResult.
        """
        from ..mac.helper import activate_app, get_frontmost_app, restore_app

        previous_app = get_frontmost_app()
        try:
            if not activate_app(target.app or "", target.pid):
                return self._failure("type_text", target, "Could not activate target application.")
            foreground_io.type_text(text, platform_name="darwin")
            return self._success("type_text", target, data={"text_length": len(text)})
        except Exception as e:
            return self._failure("type_text", target, f"Foreground type failed: {e}")
        finally:
            if previous_app:
                restore_app(previous_app)

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        """Send key combo via foreground activation + physical key events.

        Args:
            target: The target application/window.
            key_combo: Key combination string.

        Returns:
            ActionResult.
        """
        from ..mac.helper import activate_app, get_frontmost_app, restore_app

        previous_app = get_frontmost_app()
        try:
            if not activate_app(target.app or "", target.pid):
                return self._failure("key", target, "Could not activate target application.")
            foreground_io.key(key_combo, platform_name="darwin")
            return self._success("key", target, data={"key_combo": key_combo})
        except Exception as e:
            return self._failure("key", target, f"Foreground key failed: {e}")
        finally:
            if previous_app:
                restore_app(previous_app)

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        """Scroll via foreground activation + physical scroll events.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            direction: Scroll direction.
            clicks: Number of scroll clicks.

        Returns:
            ActionResult.
        """
        from ..mac.helper import activate_app, get_frontmost_app, restore_app

        previous_app = get_frontmost_app()
        try:
            if not activate_app(target.app or "", target.pid):
                return self._failure("scroll", target, "Could not activate target application.")
            foreground_io.scroll(int(x), int(y), direction, int(clicks), platform_name="darwin")
            return self._success("scroll", target, data={"direction": direction, "clicks": clicks})
        except Exception as e:
            return self._failure("scroll", target, f"Foreground scroll failed: {e}")
        finally:
            if previous_app:
                restore_app(previous_app)

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        """Not supported – foreground driver has no semantic capabilities.

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
            notes=["Foreground driver does not support semantic actions"],
        )

    def is_available(self) -> bool:
        """Available on macOS only."""
        return sys.platform == "darwin" and foreground_io.action_api_available("darwin")

    def _success(
        self,
        action: str,
        target: ComputerTarget,
        *,
        data: dict[str, Any] | None = None,
    ) -> ActionResult:
        return ActionResult(
            action=action,
            driver=self.name,
            executed=True,
            confidence="high",
            target_kind=target.kind,
            is_fallback=True,
            can_parallel_user_work=False,
            requires_foreground=True,
            uses_physical_input=True,
            visibility_state="visible_screen",
            data=data or {},
        )

    def _failure(self, action: str, target: ComputerTarget, note: str) -> ActionResult:
        return ActionResult(
            action=action,
            driver=self.name,
            executed=False,
            confidence="failed",
            target_kind=target.kind,
            is_fallback=True,
            can_parallel_user_work=False,
            requires_foreground=True,
            uses_physical_input=True,
            notes=[note],
        )
