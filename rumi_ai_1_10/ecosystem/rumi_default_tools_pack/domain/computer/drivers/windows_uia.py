"""WindowsUIADriver - semantic Windows UI Automation route."""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from ..windows.hwnd import get_window_info, resolve_hwnd
from .base import ComputerDriver


class WindowsUIADriver(ComputerDriver):
    """Driver using Windows UI Automation via optional native helpers."""

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
            can_background_click=True,
            can_background_type=True,
            can_background_scroll=True,
            can_pid_event=False,
            can_foreground_action=False,
            can_parallel_user_work=True,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        from ..windows.printwindow import capture_window_via_printwindow
        from ..windows.uia import uia_get_tree

        hwnd = self._resolve(target)
        if hwnd is None:
            return ObserveResult(
                platform="win32",
                target_window=self._target_window(target, None),
                capabilities=self._caps(),
                fallback_available=True,
            )

        return ObserveResult(
            platform="win32",
            target_window=self._target_window(target, hwnd),
            screenshot=capture_window_via_printwindow(hwnd),
            ax_tree=uia_get_tree(hwnd),
            capabilities=self._caps(),
            fallback_available=True,
        )

    def click(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> ActionResult:
        from ..windows.uia import uia_find_candidates, uia_invoke

        hwnd = self._resolve(target)
        if hwnd is None:
            return self._failure("click", target, "No HWND matched the target.")
        candidates = uia_find_candidates(hwnd, point=(x, y))
        if not candidates:
            return self._failure("click", target, f"No UIA element found at ({x}, {y}).")
        element = candidates[0]
        ok = uia_invoke(str(element.get("id") or ""))
        return ActionResult(
            action="click",
            driver=self.name,
            executed=ok,
            confidence="high" if ok else "failed",
            target_kind=target.kind,
            can_parallel_user_work=True,
            requires_foreground=False,
            uses_physical_input=False,
            data={"hwnd": hwnd, "element": element},
            notes=[] if ok else ["UIA element did not support an invoke-like pattern."],
        )

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        from ..windows.uia import uia_find_candidates, uia_set_value

        hwnd = self._resolve(target)
        if hwnd is None:
            return self._failure("type_text", target, "No HWND matched the target.")
        candidates = uia_find_candidates(hwnd, role="edit", intent="edit text input")
        if not candidates:
            candidates = uia_find_candidates(hwnd, intent="text edit")
        if not candidates:
            return self._failure("type_text", target, "No editable UIA element found.")
        element = candidates[0]
        ok = uia_set_value(str(element.get("id") or ""), text)
        return ActionResult(
            action="type_text",
            driver=self.name,
            executed=ok,
            confidence="high" if ok else "failed",
            target_kind=target.kind,
            can_parallel_user_work=True,
            requires_foreground=False,
            uses_physical_input=False,
            data={"hwnd": hwnd, "element": element, "text_length": len(text)},
            notes=[] if ok else ["UIA element did not support ValuePattern-like text setting."],
        )

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        return ActionResult(
            action="key",
            driver=self.name,
            executed=False,
            confidence="not_supported",
            target_kind=target.kind,
            notes=["UIA driver does not synthesize arbitrary key combos; use PostMessage fallback."],
        )

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        from ..windows.uia import uia_find_candidates, uia_scroll

        hwnd = self._resolve(target)
        if hwnd is None:
            return self._failure("scroll", target, "No HWND matched the target.")
        candidates = uia_find_candidates(hwnd, point=(x, y), intent="scroll")
        if not candidates:
            return self._failure("scroll", target, f"No scrollable UIA element found at ({x}, {y}).")
        element = candidates[0]
        ok = uia_scroll(str(element.get("id") or ""), direction=direction, amount=clicks)
        return ActionResult(
            action="scroll",
            driver=self.name,
            executed=ok,
            confidence="high" if ok else "failed",
            target_kind=target.kind,
            can_parallel_user_work=True,
            requires_foreground=False,
            uses_physical_input=False,
            data={"hwnd": hwnd, "element": element},
            notes=[] if ok else ["UIA element did not support ScrollPattern-like scrolling."],
        )

    def semantic_action(
        self,
        target: ComputerTarget,
        intent: str = "",
        element_or_point: Any = None,
    ) -> ActionResult:
        from ..windows.uia import uia_find_candidates, uia_invoke, uia_set_value

        hwnd = self._resolve(target)
        if hwnd is None:
            return self._failure("semantic_action", target, "No HWND matched the target.")
        if isinstance(element_or_point, dict) and element_or_point.get("id"):
            candidates = [element_or_point]
        elif isinstance(element_or_point, (tuple, list)) and len(element_or_point) >= 2:
            candidates = uia_find_candidates(hwnd, point=(int(element_or_point[0]), int(element_or_point[1])), intent=intent)
        else:
            candidates = uia_find_candidates(hwnd, intent=intent)
        if not candidates:
            return self._failure("semantic_action", target, f"No UIA element matched intent: {intent}")

        element = candidates[0]
        element_id = str(element.get("id") or "")
        if "set_value:" in intent:
            value = intent.split("set_value:", 1)[1]
            ok = uia_set_value(element_id, value)
        else:
            ok = uia_invoke(element_id)
        return ActionResult(
            action="semantic_action",
            driver=self.name,
            executed=ok,
            confidence="high" if ok else "failed",
            target_kind=target.kind,
            can_parallel_user_work=True,
            requires_foreground=False,
            uses_physical_input=False,
            data={"hwnd": hwnd, "element": element, "intent": intent},
        )

    def is_available(self) -> bool:
        return sys.platform == "win32"

    @staticmethod
    def _caps() -> dict[str, bool]:
        return {
            "can_capture_background_window": True,
            "can_semantic_action": True,
            "can_background_click": True,
            "can_background_type": True,
            "can_background_scroll": True,
            "can_parallel_user_work": True,
        }

    @staticmethod
    def _resolve(target: ComputerTarget) -> int | None:
        return resolve_hwnd(
            hwnd=target.hwnd,
            window_id=target.window_id,
            pid=target.pid,
            title=target.window_title or target.app,
        )

    @staticmethod
    def _target_window(target: ComputerTarget, hwnd: int | None) -> dict[str, Any]:
        info = get_window_info(hwnd) if hwnd else None
        return info or {
            "kind": target.kind,
            "app": target.app,
            "pid": target.pid,
            "hwnd": hwnd,
            "title": target.window_title,
        }

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
