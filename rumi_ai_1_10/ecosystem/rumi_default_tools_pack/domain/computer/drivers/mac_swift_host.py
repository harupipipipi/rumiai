"""MacSwiftHostDriver - native Swift-backed macOS Computer Use driver."""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class MacSwiftHostDriver(ComputerDriver):
    """Driver that delegates macOS screen and input primitives to Swift."""

    def __init__(self, host: Any | None = None) -> None:
        self._host = host

    @property
    def name(self) -> str:
        return "mac_swift_host"

    @property
    def platform(self) -> str:
        return "darwin"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=True,
            can_semantic_action=False,
            can_background_click=False,
            can_background_type=False,
            can_background_key=False,
            can_background_scroll=False,
            can_pid_event=False,
            can_foreground_action=True,
            can_parallel_user_work=False,
            requires_foreground_for_capture=False,
            requires_user_permission=True,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        args = self._target_args(target)
        result = self._run("computer.screenshot", args)
        return ObserveResult(
            platform="darwin",
            target_window=self._target_window(target, result),
            screenshot=result,
            capabilities={
                "can_capture_background_window": True,
                "can_foreground_action": True,
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
        args = {**self._target_args(target), "x": x, "y": y, "button": button}
        result = self._run("computer.click", args)
        return self._action_result("click", target, result, uses_physical_input=True)

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        result = self._run("computer.type", {**self._target_args(target), "text": text})
        return self._action_result("type_text", target, result, uses_physical_input=True)

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        result = self._run("computer.key", {**self._target_args(target), "key_combo": key_combo})
        return self._action_result("key", target, result, uses_physical_input=True)

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        args = {**self._target_args(target), "x": x, "y": y, "direction": direction, "amount": clicks}
        result = self._run("computer.scroll", args)
        return self._action_result("scroll", target, result, uses_physical_input=True)

    def move(self, target: ComputerTarget, x: int = 0, y: int = 0) -> ActionResult:
        result = self._run("computer.move", {**self._target_args(target), "x": x, "y": y})
        return self._action_result("move", target, result, uses_physical_input=True)

    def drag(
        self,
        target: ComputerTarget,
        x1: int = 0,
        y1: int = 0,
        x2: int = 0,
        y2: int = 0,
    ) -> ActionResult:
        args = {**self._target_args(target), "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        result = self._run("computer.drag", args)
        return self._action_result("drag", target, result, uses_physical_input=True)

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
            notes=["mac_swift_host does not provide semantic AX actions."],
        )

    def is_available(self) -> bool:
        if sys.platform != "darwin":
            return False
        try:
            return bool(self._host_instance().available())
        except Exception:
            return False

    def _host_instance(self) -> Any:
        if self._host is None:
            from ..mac.swift_host import MacSwiftComputerHost

            self._host = MacSwiftComputerHost()
        return self._host

    def _run(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        return self._host_instance().run(action, args)

    @staticmethod
    def _target_args(target: ComputerTarget) -> dict[str, Any]:
        args: dict[str, Any] = {
            "coordinate_space": target.coordinate_space,
        }
        for key in ("app", "pid", "window_id", "window_title", "bundle_id"):
            value = getattr(target, key)
            if value is not None and value != "":
                args[key] = value
        if target.window_title:
            args["title"] = target.window_title
        return args

    @staticmethod
    def _target_window(target: ComputerTarget, result: dict[str, Any]) -> dict[str, Any]:
        if isinstance(result.get("target_window"), dict):
            return dict(result["target_window"])
        return {
            "kind": target.kind,
            "app": target.app,
            "pid": target.pid,
            "window_id": target.window_id,
            "title": target.window_title,
        }

    def _action_result(
        self,
        action: str,
        target: ComputerTarget,
        result: dict[str, Any],
        *,
        uses_physical_input: bool,
    ) -> ActionResult:
        executed = bool(result.get("executed")) and not bool(result.get("is_error"))
        return ActionResult(
            action=action,
            driver=self.name,
            executed=executed,
            confidence="best_effort" if executed else "failed",
            target_kind=target.kind,
            can_parallel_user_work=False,
            requires_foreground=True,
            uses_physical_input=uses_physical_input,
            data={k: v for k, v in result.items() if k not in {"executed", "action"}},
            notes=[] if executed else [str(result.get("reason") or "macOS Swift host did not execute the action.")],
        )
