"""MacCGEventPidDriver - experimental pid-targeted CGEvent injection.

The driver only reports available when PyObjC Quartz can be imported. Actions
return success only after CGEvent calls are posted without helper failure; if
Quartz is absent or the input cannot be represented, the action fails closed.
"""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class MacCGEventPidDriver(ComputerDriver):
    """Experimental driver using CGEventPostToPid for background input."""

    @property
    def name(self) -> str:
        return "mac_cgevent_pid"

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self) -> ComputerCapabilities:
        available = self.is_available()
        return ComputerCapabilities(
            can_capture_background_window=False,
            can_semantic_action=False,
            can_background_click=available,
            can_background_type=available,
            can_background_key=available,
            can_background_scroll=available,
            can_pid_event=available,
            can_foreground_action=False,
            can_parallel_user_work=available,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        available = self.is_available()
        return ObserveResult(
            platform="darwin",
            target_window={"app": target.app, "pid": target.pid},
            capabilities={
                "can_pid_event": available,
                "can_background_click": available,
                "can_background_type": available,
                "can_background_key": available,
                "can_background_scroll": available,
            },
            fallback_available=True,
        )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        from ..mac.cgevent import post_click_to_pid

        if target.pid is None:
            return self._failure("click", target, "CGEventPostToPid requires a PID")
        try:
            success = post_click_to_pid(pid=target.pid, x=x, y=y, button=button)
            return self._result("click", target, success, "CGEventPostToPid click")
        except Exception as exc:
            return self._failure("click", target, f"CGEvent click failed: {exc}")

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        from ..mac.cgevent import post_key_to_pid

        if target.pid is None:
            return self._failure("type_text", target, "CGEventPostToPid requires a PID")
        try:
            success = post_key_to_pid(pid=target.pid, text=text)
            return self._result(
                "type_text",
                target,
                success,
                "CGEventPostToPid type",
                data={"text_length": len(text)},
            )
        except Exception as exc:
            return self._failure("type_text", target, f"CGEvent type failed: {exc}")

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        from ..mac.cgevent import post_key_to_pid

        if target.pid is None:
            return self._failure("key", target, "CGEventPostToPid requires a PID")
        try:
            success = post_key_to_pid(pid=target.pid, key_combo=key_combo)
            return self._result(
                "key",
                target,
                success,
                "CGEventPostToPid key",
                data={"key_combo": key_combo},
            )
        except Exception as exc:
            return self._failure("key", target, f"CGEvent key failed: {exc}")

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        from ..mac.cgevent import post_scroll_to_pid

        if target.pid is None:
            return self._failure("scroll", target, "CGEventPostToPid requires a PID")
        try:
            success = post_scroll_to_pid(
                pid=target.pid,
                x=x,
                y=y,
                direction=direction,
                clicks=clicks,
            )
            return self._result(
                "scroll",
                target,
                success,
                "CGEventPostToPid scroll",
                data={"direction": direction, "clicks": clicks},
            )
        except Exception as exc:
            return self._failure("scroll", target, f"CGEvent scroll failed: {exc}")

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
            notes=["CGEvent driver does not support semantic actions"],
        )

    def is_available(self) -> bool:
        if sys.platform != "darwin":
            return False
        from ..mac.cgevent import cgevent_smoke_test

        return bool(cgevent_smoke_test().get("available"))

    def _result(
        self,
        action: str,
        target: ComputerTarget,
        success: bool,
        detail: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> ActionResult:
        return ActionResult(
            action=action,
            driver=self.name,
            executed=success,
            confidence="experimental" if success else "failed",
            target_kind=target.kind,
            can_parallel_user_work=success,
            requires_foreground=False,
            uses_physical_input=False,
            notes=[
                f"EXPERIMENTAL: {detail}; some apps ignore pid-targeted events."
            ] if success else [
                f"{detail} was unavailable, unsupported, or rejected by the target process."
            ],
            data={"pid": target.pid, **(data or {})},
        )

    def _failure(self, action: str, target: ComputerTarget, note: str) -> ActionResult:
        return ActionResult(
            action=action,
            driver=self.name,
            executed=False,
            confidence="failed",
            target_kind=target.kind,
            requires_foreground=False,
            uses_physical_input=False,
            notes=[note],
        )
