"""LinuxVisibleDesktopDriver - foreground Linux desktop route."""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class LinuxVisibleDesktopDriver(ComputerDriver):
    """Driver backed by common Linux desktop utilities such as xdotool."""

    @property
    def name(self) -> str:
        return "linux_visible"

    @property
    def platform(self) -> str:
        return "linux"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=False,
            can_semantic_action=False,
            can_pid_event=False,
            can_foreground_action=True,
            can_parallel_user_work=False,
            requires_foreground_for_capture=True,
            requires_user_permission=False,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        from ..linux import xdotool

        screenshot = xdotool.screenshot(
            xdotool.temp_screenshot_path(),
            target=self._target_window(target),
        )
        return ObserveResult(
            platform="linux",
            target_window=self._target_window(target),
            screenshot=screenshot,
            capabilities={"can_foreground_action": True},
            fallback_available=True,
        )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        from ..linux import xdotool

        ok = xdotool.click(x, y, button=button)
        return self._result("click", target, ok, {"x": x, "y": y, "button": button})

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        from ..linux import xdotool

        ok = xdotool.type_text(text)
        return self._result("type_text", target, ok, {"text_length": len(text)})

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        from ..linux import xdotool

        ok = xdotool.key(key_combo)
        return self._result("key", target, ok, {"key_combo": key_combo})

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        from ..linux import xdotool

        ok = xdotool.scroll(direction, clicks)
        return self._result("scroll", target, ok, {"x": x, "y": y, "direction": direction, "clicks": clicks})

    def move(self, target: ComputerTarget, x: int = 0, y: int = 0) -> ActionResult:
        from ..linux import xdotool

        ok = xdotool.move(x, y)
        return self._result("move", target, ok, {"x": x, "y": y})

    def drag(
        self,
        target: ComputerTarget,
        x1: int = 0,
        y1: int = 0,
        x2: int = 0,
        y2: int = 0,
    ) -> ActionResult:
        from ..linux import xdotool

        ok = xdotool.drag(x1, y1, x2, y2)
        return self._result("drag", target, ok, {"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        return ActionResult(
            action="semantic_action",
            driver=self.name,
            executed=False,
            confidence="not_supported",
            target_kind=target.kind,
            notes=["linux_visible does not expose semantic accessibility actions."],
        )

    def is_available(self) -> bool:
        if not sys.platform.startswith("linux"):
            return False
        try:
            from ..linux import xdotool

            return xdotool.desktop_session_available() and xdotool.command_available("xdotool")
        except Exception:
            return False

    @staticmethod
    def _target_window(target: ComputerTarget) -> dict[str, Any]:
        return {
            "kind": target.kind,
            "app": target.app,
            "pid": target.pid,
            "window_id": target.window_id,
            "title": target.window_title,
        }

    def _result(
        self,
        action: str,
        target: ComputerTarget,
        executed: bool,
        data: dict[str, Any] | None = None,
    ) -> ActionResult:
        return ActionResult(
            action=action,
            driver=self.name,
            executed=executed,
            confidence="best_effort" if executed else "failed",
            target_kind=target.kind,
            can_parallel_user_work=False,
            requires_foreground=True,
            uses_physical_input=True,
            data=data or {},
            notes=[] if executed else ["Linux visible desktop command was unavailable or failed."],
        )
