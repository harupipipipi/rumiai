"""BrowserCDPDriver - DOM/CDP route for managed or debug-enabled browsers."""

from __future__ import annotations

import sys
from typing import Any

from ..models import ActionResult, ComputerCapabilities, ComputerTarget, ObserveResult
from .base import ComputerDriver


class BrowserCDPDriver(ComputerDriver):
    """Driver that talks to a Chrome DevTools Protocol endpoint."""

    @property
    def name(self) -> str:
        return "browser_cdp"

    @property
    def platform(self) -> str:
        return "all"

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities(
            can_capture_background_window=True,
            can_semantic_action=False,
            can_dom_action=True,
            can_background_click=True,
            can_background_type=True,
            can_background_key=True,
            can_background_scroll=True,
            can_foreground_action=False,
            can_parallel_user_work=True,
        )

    def observe(self, target: ComputerTarget) -> ObserveResult:
        from ...browser.cdp_client import BrowserCDPClient

        client = BrowserCDPClient()
        tab = client.resolve_tab(tab_id=target.browser_tab_id, url=target.url)
        if tab is None:
            return ObserveResult(platform=sys.platform, capabilities=self._caps(), fallback_available=True)
        screenshot: dict[str, Any] = {}
        dom_tree: dict[str, Any] = {}
        notes: list[str] = []
        try:
            screenshot = client.capture_screenshot(tab)
        except Exception as exc:
            notes.append(f"CDP screenshot failed: {exc}")
        try:
            dom_tree = client.dom_snapshot(tab)
        except Exception as exc:
            notes.append(f"CDP DOM snapshot failed: {exc}")
        if notes:
            dom_tree = {**dom_tree, "_notes": notes} if dom_tree else {"_notes": notes}
        return ObserveResult(
            platform=sys.platform,
            target_window={"kind": "browser_tab", "tab_id": tab.id, "title": tab.title, "url": tab.url},
            screenshot=screenshot,
            dom_tree=dom_tree,
            capabilities=self._caps(),
            recommended_next_actions=[
                {"action": "browser_cdp.click", "confidence": "high", "reason": "CDP tab is available."},
                {"action": "browser_cdp.type", "confidence": "high", "reason": "CDP tab is available."},
            ],
        )

    def click(self, target: ComputerTarget, x: int = 0, y: int = 0, button: str = "left") -> ActionResult:
        return self._with_tab(target, "click", lambda client, tab: client.click(tab, x, y, button))

    def type_text(self, target: ComputerTarget, text: str = "") -> ActionResult:
        return self._with_tab(target, "type_text", lambda client, tab: client.type_text(tab, text))

    def key(self, target: ComputerTarget, key_combo: str = "") -> ActionResult:
        key = key_combo.split("+")[-1] if key_combo else ""
        return self._with_tab(target, "key", lambda client, tab: client.press_key(tab, key))

    def scroll(
        self,
        target: ComputerTarget,
        x: int = 0,
        y: int = 0,
        direction: str = "down",
        clicks: int = 3,
    ) -> ActionResult:
        return self._with_tab(target, "scroll", lambda client, tab: client.scroll(tab, x, y, direction, clicks))

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
            notes=["BrowserCDPDriver requires explicit DOM/CDP actions or coordinates."],
        )

    def is_available(self) -> bool:
        try:
            from ...browser.cdp_client import BrowserCDPClient

            return BrowserCDPClient().is_available()
        except Exception:
            return False

    @staticmethod
    def _caps() -> dict[str, bool]:
        return {
            "can_capture_background_window": True,
            "can_dom_action": True,
            "can_background_click": True,
            "can_background_type": True,
            "can_background_key": True,
            "can_background_scroll": True,
            "can_parallel_user_work": True,
        }

    def _with_tab(self, target: ComputerTarget, action: str, fn: Any) -> ActionResult:
        from ...browser.cdp_client import BrowserCDPClient

        try:
            client = BrowserCDPClient()
            tab = client.resolve_tab(tab_id=target.browser_tab_id, url=target.url)
            if tab is None:
                return ActionResult(
                    action=action,
                    driver=self.name,
                    executed=False,
                    confidence="failed",
                    target_kind=target.kind,
                    notes=["No CDP tab matched the target."],
                )
            fn(client, tab)
            return ActionResult(
                action=action,
                driver=self.name,
                executed=True,
                confidence="high",
                target_kind=target.kind,
                can_parallel_user_work=True,
                requires_foreground=False,
                uses_physical_input=False,
                data={"tab_id": tab.id, "url": tab.url},
            )
        except Exception as exc:
            return ActionResult(
                action=action,
                driver=self.name,
                executed=False,
                confidence="failed",
                target_kind=target.kind,
                notes=[f"CDP {action} failed: {exc}"],
            )
