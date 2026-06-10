"""Tests that function entrypoints use a non-empty registry."""

from __future__ import annotations

import json
from pathlib import Path

_funcs_dir = str(Path(__file__).resolve().parent.parent / "ecosystem" / "rumi_default_tools_pack" / "functions")


def test_computer_observe_uses_factory():
    """computer_observe should use create_default_computer_seat_service, not empty DriverRegistry."""
    source = (Path(_funcs_dir) / "computer_observe" / "main.py").read_text(encoding="utf-8")
    assert "create_default_computer_seat_service" in source
    assert "DriverRegistry()" not in source


def test_computer_semantic_action_uses_factory():
    source = (Path(_funcs_dir) / "computer_semantic_action" / "main.py").read_text(encoding="utf-8")
    assert "create_default_computer_seat_service" in source
    assert "DriverRegistry()" not in source


def test_computer_pid_event_uses_factory():
    source = (Path(_funcs_dir) / "computer_pid_event" / "main.py").read_text(encoding="utf-8")
    assert "create_default_computer_seat_service" in source
    assert "DriverRegistry()" not in source


def test_computer_doctor_uses_factory():
    source = (Path(_funcs_dir) / "computer_doctor" / "main.py").read_text(encoding="utf-8")
    assert "create_default_computer_seat_service" in source
    assert "DriverRegistry()" not in source


def test_computer_observe_manifest_requires_approval():
    manifest = json.loads((Path(_funcs_dir) / "computer_observe" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["requires_approval"] is True
    assert manifest["risk_level"] == "high"
    assert "screen_capture" in manifest["capabilities"]
