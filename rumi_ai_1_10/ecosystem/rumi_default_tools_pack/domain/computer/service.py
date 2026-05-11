"""ComputerSeatService – orchestrates driver selection and fallback.

This is the main entry point for all computer actions. It selects the
best available driver, attempts the action, and falls back through the
driver chain on failure.
"""

from __future__ import annotations

import sys
import time
from dataclasses import asdict
from typing import Any

from .audit import AuditLogger
from .models import ActionResult, ComputerTarget, ObserveResult
from .permissions import requires_approval, risk_level
from .registry import DriverRegistry


class ComputerSeatService:
    """Orchestrates computer actions through the driver chain.

    Provides observe, click, type_text, key, scroll, and semantic_action
    methods that automatically select the best driver and fall back on
    failure.
    """

    def __init__(
        self,
        registry: DriverRegistry,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            registry: The driver registry to use for driver selection.
            audit_logger: Optional audit logger. Creates a default one if None.
        """
        self._registry = registry
        self._audit = audit_logger or AuditLogger()
        self._platform = sys.platform

    def observe(self, target: ComputerTarget | dict[str, Any]) -> dict[str, Any]:
        """Observe the target – returns screenshot + AX tree + capabilities.

        Args:
            target: The target to observe.

        Returns:
            Dict with platform, target_window, screenshot, ax_tree,
            capabilities, recommended_next_actions, fallback_available.
        """
        target = self._normalize_target(target)
        chain = self._registry.get_driver_chain(self._platform)

        if not chain:
            return asdict(ObserveResult(platform=self._platform))

        # Use the first available driver for observation
        for driver in chain:
            try:
                result = driver.observe(target)
                self._audit.record(
                    action="observe",
                    driver=driver.name,
                    target_app=target.app or "",
                    target_pid=target.pid,
                )
                return asdict(result)
            except Exception:
                continue

        return asdict(ObserveResult(platform=self._platform))

    def click(
        self,
        target: ComputerTarget | dict[str, Any],
        x: int = 0,
        y: int = 0,
        button: str = "left",
    ) -> dict[str, Any]:
        """Click at coordinates on the target.

        Tries AX semantic click first, then postToPid, then foreground.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            button: Mouse button ("left", "right", "middle").

        Returns:
            ActionResult as dict.
        """
        target = self._normalize_target(target)
        payload = {"x": x, "y": y, "button": button}
        return self._fallback_chain("click", target, payload)

    def type_text(
        self,
        target: ComputerTarget | dict[str, Any],
        text: str,
    ) -> dict[str, Any]:
        """Type text into the target.

        Tries AXSetValue first, then postToPid, then foreground.

        Args:
            target: The target application/window.
            text: The text to type.

        Returns:
            ActionResult as dict.
        """
        target = self._normalize_target(target)
        payload = {"text": text}
        return self._fallback_chain("type_text", target, payload)

    def key(
        self,
        target: ComputerTarget | dict[str, Any],
        key_combo: str,
    ) -> dict[str, Any]:
        """Send a key combination to the target.

        Args:
            target: The target application/window.
            key_combo: Key combination (e.g. "cmd+s", "enter").

        Returns:
            ActionResult as dict.
        """
        target = self._normalize_target(target)
        payload = {"key_combo": key_combo}
        return self._fallback_chain("key", target, payload)

    def scroll(
        self,
        target: ComputerTarget | dict[str, Any],
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> dict[str, Any]:
        """Scroll at a position on the target.

        Args:
            target: The target application/window.
            x: X coordinate.
            y: Y coordinate.
            direction: Scroll direction ("up", "down", "left", "right").
            clicks: Number of scroll clicks.

        Returns:
            ActionResult as dict.
        """
        target = self._normalize_target(target)
        payload = {"x": x, "y": y, "direction": direction, "clicks": clicks}
        return self._fallback_chain("scroll", target, payload)

    def semantic_action(
        self,
        target: ComputerTarget | dict[str, Any],
        intent: str = "",
        element_or_point: Any = None,
    ) -> dict[str, Any]:
        """Execute a semantic action (e.g. 'press the Save button').

        Args:
            target: The target application/window.
            intent: Natural language intent description.
            element_or_point: The AX element or coordinate to act on.

        Returns:
            ActionResult as dict.
        """
        target = self._normalize_target(target)
        payload = {"intent": intent, "element_or_point": element_or_point}
        return self._fallback_chain("semantic_action", target, payload)

    def doctor(self) -> dict[str, Any]:
        """Check platform capabilities and driver availability.

        Returns:
            Dict with platform info, available drivers, and their capabilities.
        """
        chain = self._registry.get_driver_chain(self._platform)
        drivers_info = []
        for driver in chain:
            caps = driver.capabilities()
            drivers_info.append({
                "name": driver.name,
                "platform": driver.platform,
                "available": driver.is_available(),
                "capabilities": asdict(caps),
            })

        all_drivers = self._registry.all_drivers
        unavailable = [
            {"name": name, "platform": d.platform, "available": False}
            for name, d in all_drivers.items()
            if not d.is_available()
        ]

        return {
            "platform": self._platform,
            "available_drivers": drivers_info,
            "unavailable_drivers": unavailable,
            "driver_chain_order": [d.name for d in chain],
        }

    def _fallback_chain(
        self,
        action: str,
        target: ComputerTarget,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Try each driver in the chain until one succeeds.

        Args:
            action: The action name.
            target: The target.
            payload: Action-specific parameters.

        Returns:
            ActionResult as dict from the first successful driver,
            or a failure result if all drivers fail.
        """
        chain = self._registry.get_driver_chain(self._platform)
        errors: list[str] = []
        is_fallback = False

        for driver in chain:
            try:
                method = getattr(driver, action, None)
                if method is None:
                    continue

                # Call the appropriate method with the right arguments
                result: ActionResult = self._dispatch(method, target, payload)

                if result.executed:
                    result.is_fallback = is_fallback
                    self._audit.record(
                        action=action,
                        driver=driver.name,
                        target_app=target.app or "",
                        target_pid=target.pid,
                        intent=payload.get("intent", ""),
                        approval_required=requires_approval(action),
                        result=asdict(result),
                    )
                    return asdict(result)

            except Exception as e:
                errors.append(f"{driver.name}: {e}")
                is_fallback = True
                continue

        # All drivers failed
        failure = ActionResult(
            action=action,
            driver="none",
            executed=False,
            confidence="failed",
            notes=errors or ["No available driver for this action"],
        )
        self._audit.record(
            action=action,
            driver="none",
            target_app=target.app or "",
            target_pid=target.pid,
            approval_required=requires_approval(action),
            result=asdict(failure),
        )
        return asdict(failure)

    def _dispatch(
        self,
        method: Any,
        target: ComputerTarget,
        payload: dict[str, Any],
    ) -> ActionResult:
        """Dispatch an action method with the correct arguments.

        Args:
            method: The driver method to call.
            target: The target.
            payload: Action-specific parameters.

        Returns:
            ActionResult from the driver method.
        """
        # Determine which arguments the method expects based on action name
        method_name = method.__func__.__name__ if hasattr(method, "__func__") else ""

        if method_name == "click":
            return method(
                target,
                x=payload.get("x", 0),
                y=payload.get("y", 0),
                button=payload.get("button", "left"),
            )
        elif method_name == "type_text":
            return method(target, text=payload.get("text", ""))
        elif method_name == "key":
            return method(target, key_combo=payload.get("key_combo", ""))
        elif method_name == "scroll":
            return method(
                target,
                x=payload.get("x", 0),
                y=payload.get("y", 0),
                direction=payload.get("direction", "down"),
                clicks=payload.get("clicks", 3),
            )
        elif method_name == "semantic_action":
            return method(
                target,
                intent=payload.get("intent", ""),
                element_or_point=payload.get("element_or_point"),
            )
        else:
            # Generic fallback – pass target and payload
            return method(target, **payload)

    @staticmethod
    def _normalize_target(
        target: ComputerTarget | dict[str, Any],
    ) -> ComputerTarget:
        """Normalize a target to a ComputerTarget instance.

        Args:
            target: Either a ComputerTarget or a dict.

        Returns:
            A ComputerTarget instance.
        """
        if isinstance(target, ComputerTarget):
            return target
        return ComputerTarget(
            app=target.get("app"),
            pid=target.get("pid"),
            window_id=target.get("window_id"),
            window_title=target.get("window_title"),
        )
