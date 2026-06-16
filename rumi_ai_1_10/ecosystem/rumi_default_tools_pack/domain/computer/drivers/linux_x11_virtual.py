"""LinuxX11VirtualDriver - private Xvfb-backed Linux Computer Use route."""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class LinuxX11VirtualDriver(ComputerDriver):
    """Driver backed by a rumiai-owned Xvfb/Openbox virtual desktop."""

    def __init__(self, session: Any | None = None) -> None:
        self._session = session

    @property
    def name(self) -> str:
        return "linux_x11_virtual"

    @property
    def platform(self) -> str:
        return "linux"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=True,
            can_capture_hidden_window=False,
            can_semantic_action=False,
            can_dom_action=False,
            can_background_click=True,
            can_background_type=True,
            can_background_key=True,
            can_background_scroll=True,
            can_pid_event=False,
            can_foreground_action=False,
            can_parallel_user_work=True,
            requires_foreground_for_capture=False,
            requires_user_permission=False,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        screenshot = self._session_instance().screenshot()
        return ObserveResult(
            platform="linux",
            target_window=self._target_window(target),
            screenshot=screenshot,
            capabilities=self._capabilities_dict(),
            fallback_available=True,
        )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        result = self._session_instance().click(x, y, button=button)
        return self._action_result("click", target, result, {"x": x, "y": y, "button": button})

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        result = self._session_instance().type(text)
        return self._action_result("type_text", target, result, {"text_length": len(text)})

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        result = self._session_instance().keypress(key_combo)
        return self._action_result("key", target, result, {"key_combo": key_combo})

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        result = self._session_instance().scroll(x, y, direction=direction, clicks=clicks)
        return self._action_result("scroll", target, result, {"x": x, "y": y, "direction": direction, "clicks": clicks})

    def move(self, target: ComputerTarget, x: int = 0, y: int = 0) -> ActionResult:
        result = self._session_instance().move(x, y)
        return self._action_result("move", target, result, {"x": x, "y": y})

    def drag(
        self,
        target: ComputerTarget,
        x1: int = 0,
        y1: int = 0,
        x2: int = 0,
        y2: int = 0,
    ) -> ActionResult:
        result = self._session_instance().drag(x1, y1, x2, y2)
        return self._action_result("drag", target, result, {"x1": x1, "y1": y1, "x2": x2, "y2": y2})

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
            can_parallel_user_work=True,
            requires_foreground=False,
            uses_physical_input=False,
            notes=["linux_x11_virtual does not expose semantic accessibility actions."],
        )

    def is_available(self) -> bool:
        if not sys.platform.startswith("linux"):
            return False
        try:
            return bool(self._session_instance().is_available())
        except Exception:
            return False

    def _session_instance(self) -> Any:
        if self._session is None:
            from ..linux.x11_virtual import X11VirtualSession

            self._session = X11VirtualSession()
        return self._session

    def _target_window(self, target: ComputerTarget) -> dict[str, Any]:
        session = self._session_instance()
        return {
            "kind": target.kind,
            "app": target.app,
            "pid": target.pid,
            "window_id": target.window_id,
            "title": target.window_title,
            "display": getattr(session, "display", None),
            "virtual": True,
        }

    def _capabilities_dict(self) -> dict[str, bool]:
        caps = self.capabilities()
        return {
            "can_capture_background_window": caps.can_capture_background_window,
            "can_capture_hidden_window": caps.can_capture_hidden_window,
            "can_semantic_action": caps.can_semantic_action,
            "can_dom_action": caps.can_dom_action,
            "can_background_click": caps.can_background_click,
            "can_background_type": caps.can_background_type,
            "can_background_key": caps.can_background_key,
            "can_background_scroll": caps.can_background_scroll,
            "can_pid_event": caps.can_pid_event,
            "can_foreground_action": caps.can_foreground_action,
            "can_parallel_user_work": caps.can_parallel_user_work,
            "requires_foreground_for_capture": caps.requires_foreground_for_capture,
            "requires_user_permission": caps.requires_user_permission,
        }

    def _action_result(
        self,
        action: str,
        target: ComputerTarget,
        result: dict[str, Any],
        data: dict[str, Any] | None = None,
    ) -> ActionResult:
        executed = bool(result.get("executed"))
        reason = str(result.get("reason") or result.get("error") or result.get("stderr") or "")
        return ActionResult(
            action=action,
            driver=self.name,
            executed=executed,
            confidence="best_effort" if executed else "failed",
            target_kind=target.kind,
            can_parallel_user_work=True,
            requires_foreground=False,
            uses_physical_input=False,
            visibility_state="virtual_display",
            render_state="x11_virtual",
            data={**(data or {}), "session": result},
            notes=[] if executed else [reason or "Linux X11 virtual session did not execute the action."],
        )
