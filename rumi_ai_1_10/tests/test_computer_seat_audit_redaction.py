"""Security coverage for the legacy ComputerSeat diagnostic audit sink."""

from __future__ import annotations

import json
import os
import stat

import pytest

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.audit import AuditLogger
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.models import (
    ActionResult,
    ComputerCapabilities,
)
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.registry import DriverRegistry
from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.service import ComputerSeatService


_AUDIT_FIELDS = {
    "timestamp_ms",
    "action",
    "driver",
    "approval_required",
    "target_app_present",
    "target_bundle_present",
    "target_pid_present",
    "target_window_present",
    "executed",
    "result_ok",
    "is_fallback",
    "can_parallel_user_work",
    "requires_foreground",
    "uses_physical_input",
}


class _CanaryDriver:
    name = "audit_test_driver"
    platform = "test"

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> ComputerCapabilities:
        return ComputerCapabilities()

    def type_text(self, target, text: str = "") -> ActionResult:
        return ActionResult(
            action="type_text",
            driver=self.name,
            executed=True,
            data={
                "text": text,
                "value": text,
                "error": f"driver-error-{text}",
                "ax_handle": f"AXUIElement-{text}",
            },
            notes=[f"driver-note-{text}"],
        )

    def semantic_action(self, target, intent: str = "", element_or_point=None) -> ActionResult:
        return ActionResult(
            action="semantic_action",
            driver=self.name,
            executed=True,
            data={
                "intent": intent,
                "selected_element": element_or_point,
                "error": f"driver-error-{intent}",
            },
            notes=[f"driver-note-{intent}"],
        )


def test_computer_seat_audit_redacts_payload_target_and_result_canaries(tmp_path):
    canary = "CANARY_private-content_42"
    log_path = tmp_path / "computer-seat-audit.jsonl"
    registry = DriverRegistry()
    registry.register(_CanaryDriver())
    service = ComputerSeatService(registry, audit_logger=AuditLogger(log_path))
    service._platform = "test"

    target = {
        "app": f"{canary}-application",
        "bundle_id": f"{canary}.bundle",
        "pid": 424242,
        "window_id": 777,
        "window_title": f"{canary}-window-title",
        "url": f"https://{canary}.example.test/private-path",
    }
    service.type_text(target, canary)
    service.semantic_action(
        target,
        intent=canary,
        element_or_point={
            "id": f"{canary}-element-id",
            "title": f"{canary}-element-title",
            "value": canary,
            "ax_handle": f"AXUIElement-{canary}",
        },
    )

    serialized = log_path.read_text(encoding="utf-8")
    events = [json.loads(line) for line in serialized.splitlines()]
    assert canary not in serialized
    assert [event["action"] for event in events] == ["type_text", "semantic_action"]
    for event in events:
        assert set(event) == _AUDIT_FIELDS
        assert isinstance(event["timestamp_ms"], int)
        assert event["driver"] == "audit_test_driver"
        assert event["target_app_present"] is True
        assert event["target_bundle_present"] is True
        assert event["target_pid_present"] is True
        assert event["target_window_present"] is True
        assert event["executed"] is True
        assert event["result_ok"] is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX owner-only mode semantics are required")
def test_computer_seat_audit_file_is_owner_only_after_create_and_append(tmp_path):
    log_path = tmp_path / "computer-seat-audit.jsonl"
    log_path.touch(mode=0o644)
    os.chmod(log_path, 0o644)

    AuditLogger(log_path).record(action="click", driver="audit_test_driver")

    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600
