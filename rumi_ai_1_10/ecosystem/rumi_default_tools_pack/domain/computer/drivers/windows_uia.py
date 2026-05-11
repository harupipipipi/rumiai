"""WindowsUIADriver – UI Automation skeleton.

Skeleton driver for Windows UI Automation API. This will provide
semantic interaction with Windows applications through the UIA tree.

⚠️ SKELETON: Not yet implemented. All methods raise NotImplementedError
or return stub results.
"""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class WindowsUIADriver(ComputerDriver):
    """Skeleton driver for Windows UI Automation.

    ⚠️ SKELETON: Not yet implemented for Windows platform.
    """

    @property
    def name(self) -> str:
        return "windows_uia"

    @property
    def platform(self) -> str:
        return "win32"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=True,
            can_semantic_action=True,
            can_pid_event=False,
            can_foreground_action=False,
            can_parallel_user_work=True,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        """Observe via UIA tree.

        Args:
            target: The target to observe.

        Returns:
            ObserveResult stub.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError("WindowsUIADriver.observe is not yet implemented")

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        """Click via UIA InvokePattern.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            button: Mouse button.

        Returns:
            ActionResult stub.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError("WindowsUIADriver.click is not yet implemented")

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        """Type text via UIA ValuePattern.

        Args:
            target: The target application/window.
            text: The text to type.

        Returns:
            ActionResult stub.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError("WindowsUIADriver.type_text is not yet implemented")

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        """Send key combo via UIA.

        Args:
            target: The target application/window.
            key_combo: Key combination string.

        Returns:
            ActionResult stub.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError("WindowsUIADriver.key is not yet implemented")

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        """Scroll via UIA ScrollPattern.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            direction: Scroll direction.
            clicks: Number of scroll clicks.

        Returns:
            ActionResult stub.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError("WindowsUIADriver.scroll is not yet implemented")

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        """Execute semantic action via UIA patterns.

        Args:
            target: The target application/window.
            intent: Natural language intent.
            element_or_point: Element or point.

        Returns:
            ActionResult stub.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError(
            "WindowsUIADriver.semantic_action is not yet implemented"
        )

    def is_available(self) -> bool:
        """Available on Windows only (when implemented)."""
        return sys.platform == "win32"
