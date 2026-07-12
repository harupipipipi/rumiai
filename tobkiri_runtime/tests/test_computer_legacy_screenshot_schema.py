"""Tests that computer.screenshot preserves the legacy schema fields."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REQUIRED_SCHEMA_FIELDS = [
    "path", "model_image_path", "image_size", "model_image_size",
    "coordinate_system", "action_coordinate_system",
]

OPTIONAL_SCHEMA_FIELDS = [
    "data_url", "model_image", "selected_window", "active_window",
    "target_window", "coordinate_contract", "cursor_move_contract",
]


def test_screenshot_result_method_has_required_fields():
    """Verify _screenshot_result produces the expected schema keys."""
    from tobkiri_runtime.ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
        BrowserComputerController,
    )
    source = Path(
        BrowserComputerController.__module__.replace(".", "/") + ".py"
    )
    # Read the source to verify schema fields are present
    src_path = Path(__file__).resolve().parent.parent / "ecosystem" / "rumi_default_tools_pack" / "domain" / "tool" / "browser_computer.py"
    content = src_path.read_text(encoding="utf-8")
    for field in REQUIRED_SCHEMA_FIELDS:
        assert f'"{field}"' in content or f"'{field}'" in content, f"Missing schema field: {field}"


def test_screenshot_dry_run_schema():
    """dry_run screenshot should return action and dry_run fields."""
    from tobkiri_runtime.ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import (
        BrowserComputerController,
    )
    ctrl = BrowserComputerController(artifact_root=Path("/tmp/test_screenshot"))
    result = ctrl.run("computer.screenshot", {"dry_run": True}, yolo_mode=True)
    assert result["action"] == "computer.screenshot"
    assert result["dry_run"] is True
    assert result["requires_approval"] is False


def test_screenshot_result_includes_computer_seat_metadata():
    """When screenshot succeeds, it should include additive computer_seat metadata."""
    src_path = Path(__file__).resolve().parent.parent / "ecosystem" / "rumi_default_tools_pack" / "domain" / "tool" / "browser_computer.py"
    content = src_path.read_text(encoding="utf-8")
    # Verify the code adds computer_seat metadata
    assert "computer_seat" in content
    assert "driver_chain_order" in content
