"""WindowsPostMessageDriver – PostMessage/SendMessage skeleton.

Skeleton driver for Windows PostMessage/SendMessage API. This will
provide background input injection to specific window handles.

⚠️ SKELETON: Not yet implemented. All methods raise NotImplementedError
or return stub results.
"""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class WindowsPostMessageDriver(ComputerDriver):
    """Skeleton driver for Windows PostMessage/SendMessage.

    ⚠️ SKELETON: Not yet implemented for Windows platform.
    """

    @property
    def name(self) -> str:
        return "windows_postmessage"

    @property
    def platform(self) -> str:
        return "win32"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=False,
            can_semantic_action=False,
            can_pid_event=True,
            can_foreground_action=False,
            can_parallel_user_work=True,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        """PostMessage driver does not support observation.

        Args:
            target: The target to observe.

        Returns:
            ObserveResult stub.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError(
            "WindowsPostMessageDriver.observe is not yet implemented"
        )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        """Click via PostMessage WM_LBUTTONDOWN/UP.

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
        raise NotImplementedError(
            "WindowsPostMessageDriver.click is not yet implemented"
        )

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        """Type text via PostMessage WM_CHAR.

        Args:
            target: The target application/window.
            text: The text to type.

        Returns:
            ActionResult stub.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError(
            "WindowsPostMessageDriver.type_text is not yet implemented"
        )

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        """Send key combo via PostMessage WM_KEYDOWN/UP.

        Args:
            target: The target application/window.
            key_combo: Key combination string.

        Returns:
            ActionResult stub.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError(
            "WindowsPostMessageDriver.key is not yet implemented"
        )

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        """Scroll via PostMessage WM_MOUSEWHEEL.

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
        raise NotImplementedError(
            "WindowsPostMessageDriver.scroll is not yet implemented"
        )

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        """Not supported – PostMessage has no semantic capabilities.

        Args:
            target: The target application/window.
            intent: Intent description.
            element_or_point: Element or point.

        Returns:
            ActionResult with executed=False.

        Raises:
            NotImplementedError: Always (skeleton).
        """
        raise NotImplementedError(
            "WindowsPostMessageDriver.semantic_action is not yet implemented"
        )

    def is_available(self) -> bool:
        """Available on Windows only (when implemented)."""
        return sys.platform == "win32"
