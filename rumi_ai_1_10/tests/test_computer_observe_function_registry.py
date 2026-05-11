"""Tests that function entrypoints use a non-empty registry."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_funcs_dir = str(Path(__file__).resolve().parent.parent / "ecosystem" / "rumi_default_tools_pack" / "functions")
if _funcs_dir not in sys.path:
    sys.path.insert(0, _funcs_dir)

_domain_dir = str(Path(__file__).resolve().parent.parent / "ecosystem" / "rumi_default_tools_pack")
if _domain_dir not in sys.path:
    sys.path.insert(0, _domain_dir)


def test_computer_observe_uses_factory():
    """computer_observe should use create_default_computer_seat_service, not empty DriverRegistry."""
    source = (Path(_funcs_dir) / "computer_observe" / "main.py").read_text()
    assert "create_default_computer_seat_service" in source
    assert "DriverRegistry()" not in source


def test_computer_semantic_action_uses_factory():
    source = (Path(_funcs_dir) / "computer_semantic_action" / "main.py").read_text()
    assert "create_default_computer_seat_service" in source
    assert "DriverRegistry()" not in source


def test_computer_pid_event_uses_factory():
    source = (Path(_funcs_dir) / "computer_pid_event" / "main.py").read_text()
    assert "create_default_computer_seat_service" in source
    assert "DriverRegistry()" not in source


def test_computer_doctor_uses_factory():
    source = (Path(_funcs_dir) / "computer_doctor" / "main.py").read_text()
    assert "create_default_computer_seat_service" in source
    assert "DriverRegistry()" not in source
