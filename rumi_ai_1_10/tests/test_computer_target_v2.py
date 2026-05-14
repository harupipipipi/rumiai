from __future__ import annotations

from dataclasses import asdict

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ActionResult,
    ComputerCapabilities,
    ComputerTarget,
    ObserveResult,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.registry import (
    MAC_DRIVER_ORDER,
    WINDOWS_DRIVER_ORDER,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.service import (
    ComputerSeatService,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.registry import (
    DriverRegistry,
)


def test_computer_target_v2_defaults_keep_legacy_shape():
    target = ComputerTarget(app="Notepad", pid=123)

    assert target.kind == "desktop"
    assert target.app == "Notepad"
    assert target.pid == 123
    assert target.coordinate_space == "window"
    assert "hwnd" in asdict(target)
    assert "browser_tab_id" in asdict(target)


def test_action_result_exposes_background_truth_fields():
    result = ActionResult(
        action="click",
        driver="windows_postmessage",
        executed=True,
        confidence="best_effort",
        target_kind="window",
        can_parallel_user_work=True,
        requires_foreground=False,
        uses_physical_input=False,
        visibility_state="visible",
        render_state="ok",
    )

    data = asdict(result)
    assert data["target_kind"] == "window"
    assert data["can_parallel_user_work"] is True
    assert data["requires_foreground"] is False
    assert data["uses_physical_input"] is False


def test_capability_matrix_adds_dom_and_background_flags():
    caps = asdict(ComputerCapabilities(can_dom_action=True, can_background_click=True))

    assert caps["can_dom_action"] is True
    assert caps["can_background_click"] is True
    assert caps["can_capture_background_window"] is False


def test_driver_orders_include_browser_first_and_fallback_last():
    assert MAC_DRIVER_ORDER[:2] == ["browser_cdp", "browser_companion"]
    assert WINDOWS_DRIVER_ORDER[:2] == ["browser_cdp", "browser_companion"]
    assert WINDOWS_DRIVER_ORDER[-1] == "local_visible"


def test_service_normalizes_v2_target_dict():
    target = ComputerSeatService._normalize_target({
        "kind": "browser_tab",
        "client_id": "client-1",
        "tab_id": 42,
        "hwnd": 100,
        "title": "LINE",
        "coordinate_space": "viewport",
    })

    assert target.kind == "browser_tab"
    assert target.browser_client_id == "client-1"
    assert target.browser_tab_id == 42
    assert target.hwnd == 100
    assert target.window_title == "LINE"
    assert target.coordinate_space == "viewport"


class _DomDriver:
    name = "browser_cdp"
    platform = "test"

    def is_available(self):
        return True

    def capabilities(self):
        return ComputerCapabilities(can_dom_action=True, can_background_click=True, can_parallel_user_work=True)

    def observe(self, target):
        return ObserveResult(platform="test", dom_tree={"nodes": [{"id": 1}]})


def test_observe_aggregates_dom_tree_and_recommendations():
    registry = DriverRegistry()
    registry.register(_DomDriver())
    service = ComputerSeatService(registry)
    service._platform = "test"

    result = service.observe({"kind": "browser_tab"})

    assert result["dom_tree"] == {"nodes": [{"id": 1}]}
    assert result["capabilities"]["can_dom_action"] is True
    assert result["recommended_next_actions"][0]["action"] == "browser_cdp.click"
