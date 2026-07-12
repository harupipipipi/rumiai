"""WindowsPostMessageDriver - best-effort Win32 message route."""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from ..windows.hwnd import get_window_info, resolve_hwnd
from .base import ComputerDriver


class WindowsPostMessageDriver(ComputerDriver):
    """Driver that posts Win32 messages to a target HWND."""

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
            can_background_click=True,
            can_background_type=True,
            can_background_key=True,
            can_background_scroll=True,
            can_pid_event=True,
            can_foreground_action=False,
            can_parallel_user_work=True,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        hwnd = self._resolve(target)
        return ObserveResult(
            platform="win32",
            target_window=get_window_info(hwnd) if hwnd else {"app": target.app, "pid": target.pid, "hwnd": hwnd},
            capabilities={
                "can_pid_event": True,
                "can_background_click": True,
                "can_background_type": True,
                "can_background_key": True,
                "can_background_scroll": True,
                "can_parallel_user_work": True,
            },
            fallback_available=True,
        )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
        *,
        coordinate_space: str | None = None,
    ) -> ActionResult:
        from ..windows.messages import post_click, resolve_client_point

        hwnd = self._resolve(target)
        if hwnd is None:
            return self._failure("click", target, "No HWND matched the target.")
        space = coordinate_space or target.coordinate_space
        client_x, client_y, point_data = resolve_client_point(
            hwnd,
            x,
            y,
            coordinate_space=space,
        )
        ok = post_click(hwnd, client_x, client_y, button)
        return self._result("click", target, hwnd, ok, data=point_data)

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        from ..windows.messages import post_text

        hwnd = self._resolve(target)
        if hwnd is None:
            return self._failure("type_text", target, "No HWND matched the target.")
        ok = post_text(hwnd, text)
        return self._result("type_text", target, hwnd, ok, data={"text_length": len(text)})

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        from ..windows.messages import post_key

        hwnd = self._resolve(target)
        if hwnd is None:
            return self._failure("key", target, "No HWND matched the target.")
        ok = post_key(hwnd, key_combo)
        return self._result("key", target, hwnd, ok, data={"key_combo": key_combo})

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
        *,
        coordinate_space: str | None = None,
    ) -> ActionResult:
        from ..windows.messages import post_scroll, resolve_screen_point

        hwnd = self._resolve(target)
        if hwnd is None:
            return self._failure("scroll", target, "No HWND matched the target.")
        space = coordinate_space or target.coordinate_space
        _screen_x, _screen_y, point_data = resolve_screen_point(
            hwnd,
            x,
            y,
            coordinate_space=space,
        )
        ok = post_scroll(
            hwnd,
            x,
            y,
            direction=direction,
            clicks=clicks,
            coordinate_space=space,
        )
        return self._result(
            "scroll",
            target,
            hwnd,
            ok,
            data={**point_data, "direction": direction, "clicks": clicks},
        )

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
            notes=["PostMessage does not expose semantic UI elements."],
        )

    def is_available(self) -> bool:
        return sys.platform == "win32"

    @staticmethod
    def _resolve(target: ComputerTarget) -> int | None:
        return resolve_hwnd(
            hwnd=target.hwnd,
            window_id=target.window_id,
            pid=target.pid,
            title=target.window_title or target.app,
        )

    def _result(
        self,
        action: str,
        target: ComputerTarget,
        hwnd: int,
        ok: bool,
        *,
        data: dict[str, Any] | None = None,
    ) -> ActionResult:
        return ActionResult(
            action=action,
            driver=self.name,
            executed=ok,
            confidence="best_effort" if ok else "failed",
            target_kind=target.kind,
            can_parallel_user_work=True,
            requires_foreground=False,
            uses_physical_input=False,
            notes=[
                "PostMessage was posted, but the target app may ignore synthetic messages.",
                "Windows UIPI may block higher-integrity targets.",
            ] if ok else ["PostMessage failed or was blocked."],
            data={"hwnd": hwnd, **(data or {})},
        )

    def _failure(self, action: str, target: ComputerTarget, note: str) -> ActionResult:
        return ActionResult(
            action=action,
            driver=self.name,
            executed=False,
            confidence="failed",
            target_kind=target.kind,
            can_parallel_user_work=True,
            requires_foreground=False,
            uses_physical_input=False,
            notes=[note],
        )
