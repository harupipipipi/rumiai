"""MacScreenCaptureDriver – ScreenCaptureKit / screencapture wrapper.

Captures window screenshots without requiring the window to be in the
foreground. Uses ScreenCaptureKit (macOS 12.3+) when available, falling
back to the screencapture CLI tool.
"""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class MacScreenCaptureDriver(ComputerDriver):
    """Driver for background window capture on macOS.

    This driver only supports observation (screenshot capture). It cannot
    perform input actions. Use it in combination with other drivers that
    handle input.
    """

    @property
    def name(self) -> str:
        return "mac_screen_capture"

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=True,
            can_semantic_action=False,
            can_pid_event=False,
            can_foreground_action=False,
            can_parallel_user_work=True,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        """Capture a screenshot of the target window (background-safe).

        Uses ScreenCaptureKit or screencapture -l <window_id>.

        Args:
            target: The target to observe.

        Returns:
            ObserveResult with screenshot data.
        """
        from ..mac.screencapture import capture_window

        try:
            screenshot_data = capture_window(
                window_id=target.window_id,
                pid=target.pid,
                app=target.app,
            )
            return ObserveResult(
                platform="darwin",
                target_window={"app": target.app, "pid": target.pid},
                screenshot=screenshot_data,
                capabilities={"can_capture_background_window": True},
                fallback_available=True,
            )
        except Exception as e:
            return ObserveResult(
                platform="darwin",
                target_window={"app": target.app, "pid": target.pid},
                screenshot={"error": str(e)},
                fallback_available=True,
            )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        """Not supported – this is an observation-only driver."""
        return ActionResult(
            action="click",
            driver=self.name,
            executed=False,
            notes=["MacScreenCaptureDriver is observation-only"],
        )

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        """Not supported – this is an observation-only driver."""
        return ActionResult(
            action="type_text",
            driver=self.name,
            executed=False,
            notes=["MacScreenCaptureDriver is observation-only"],
        )

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        """Not supported – this is an observation-only driver."""
        return ActionResult(
            action="key",
            driver=self.name,
            executed=False,
            notes=["MacScreenCaptureDriver is observation-only"],
        )

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        """Not supported – this is an observation-only driver."""
        return ActionResult(
            action="scroll",
            driver=self.name,
            executed=False,
            notes=["MacScreenCaptureDriver is observation-only"],
        )

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        """Not supported – this is an observation-only driver."""
        return ActionResult(
            action="semantic_action",
            driver=self.name,
            executed=False,
            notes=["MacScreenCaptureDriver is observation-only"],
        )

    def is_available(self) -> bool:
        """Available on macOS only."""
        return sys.platform == "darwin"
