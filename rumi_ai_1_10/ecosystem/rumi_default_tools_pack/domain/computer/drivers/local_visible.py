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
from . import foreground_io


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
        action_available = foreground_io.action_api_available()
        capture_available = foreground_io.capture_api_available()
        return ComputerCapabilities(
            can_capture_background_window=False,
            can_semantic_action=False,
            can_pid_event=False,
            can_foreground_action=action_available,
            can_parallel_user_work=False,
            requires_foreground_for_capture=capture_available,
            requires_user_permission=sys.platform == "darwin" and (action_available or capture_available),
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        """Observe by taking a screenshot of the visible desktop.

        Args:
            target: The target to observe.

        Returns:
            ObserveResult with screenshot data.
        """
        if not foreground_io.capture_api_available():
            return ObserveResult(
                platform=sys.platform,
                target_window={"app": target.app, "pid": target.pid},
                screenshot={
                    "method": "unavailable",
                    "error": "Visible-screen capture is supported only when the platform screenshot API is available.",
                },
                capabilities={
                    "can_capture_background_window": False,
                    "can_foreground_action": foreground_io.action_api_available(),
                    "requires_foreground_for_capture": False,
                },
                fallback_available=False,
            )
        try:
            screenshot = foreground_io.capture_visible_screen()
        except Exception as exc:
            screenshot = {"method": "unavailable", "error": str(exc)}
        return ObserveResult(
            platform=sys.platform,
            target_window={"app": target.app, "pid": target.pid},
            screenshot=screenshot,
            capabilities={
                "can_capture_background_window": False,
                "can_foreground_action": foreground_io.action_api_available(),
                "requires_foreground_for_capture": True,
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
        return self._run_foreground_action(
            "click",
            target,
            lambda: foreground_io.click(int(x), int(y), button),
        )

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        """Type text using physical keyboard events (foreground required).

        Args:
            target: The target application/window.
            text: The text to type.

        Returns:
            ActionResult.
        """
        return self._run_foreground_action(
            "type_text",
            target,
            lambda: foreground_io.type_text(text),
        )

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        """Send key combo using physical keyboard events.

        Args:
            target: The target application/window.
            key_combo: Key combination string.

        Returns:
            ActionResult.
        """
        return self._run_foreground_action(
            "key",
            target,
            lambda: foreground_io.key(key_combo),
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
        return self._run_foreground_action(
            "scroll",
            target,
            lambda: foreground_io.scroll(int(x), int(y), direction, int(clicks)),
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

    def move(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
    ) -> ActionResult:
        """Move the visible cursor using physical input."""
        return self._run_foreground_action(
            "move",
            target,
            lambda: foreground_io.move(int(x), int(y)),
        )

    def is_available(self) -> bool:
        """Available only when the host exposes a real visible-screen API."""
        return foreground_io.action_api_available() or foreground_io.capture_api_available()

    def _run_foreground_action(
        self,
        action: str,
        target: ComputerTarget,
        fn: Any,
    ) -> ActionResult:
        if not foreground_io.action_api_available():
            return ActionResult(
                action=action,
                driver=self.name,
                executed=False,
                confidence="not_supported",
                target_kind=target.kind,
                requires_foreground=True,
                uses_physical_input=True,
                can_parallel_user_work=False,
                notes=["No visible-screen automation API is available on this platform."],
            )
        try:
            fn()
            return ActionResult(
                action=action,
                driver=self.name,
                executed=True,
                confidence="high",
                target_kind=target.kind,
                requires_foreground=True,
                uses_physical_input=True,
                can_parallel_user_work=False,
                visibility_state="visible_screen",
            )
        except foreground_io.ForegroundAutomationUnavailable as exc:
            return ActionResult(
                action=action,
                driver=self.name,
                executed=False,
                confidence="not_supported",
                target_kind=target.kind,
                requires_foreground=True,
                uses_physical_input=True,
                can_parallel_user_work=False,
                notes=[str(exc)],
            )
        except Exception as exc:
            return ActionResult(
                action=action,
                driver=self.name,
                executed=False,
                confidence="failed",
                target_kind=target.kind,
                requires_foreground=True,
                uses_physical_input=True,
                can_parallel_user_work=False,
                notes=[f"Visible-screen {action} failed: {exc}"],
            )
