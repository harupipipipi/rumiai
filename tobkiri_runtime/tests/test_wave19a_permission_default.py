"""
W19-A: VULN-C05 – PermissionManager デフォルト連動テスト

RUMI_SECURITY_MODE と RUMI_PERMISSION_MODE の連動ロジックを検証する。
"""
from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest

from core_runtime.permission_manager import PermissionManager


_LINKED_VARS = ("RUMI_SECURITY_MODE", "RUMI_PERMISSION_MODE")


def _make_pm(env: dict) -> PermissionManager:
    clean = {k: v for k, v in os.environ.items() if k not in _LINKED_VARS}
    clean.update(env)
    with patch.dict(os.environ, clean, clear=True):
        return PermissionManager()


def test_strict_no_perm_mode_defaults_to_secure():
    pm = _make_pm({"RUMI_SECURITY_MODE": "strict"})
    assert pm.get_mode() == "secure"

def test_strict_explicit_secure():
    pm = _make_pm({"RUMI_SECURITY_MODE": "strict", "RUMI_PERMISSION_MODE": "secure"})
    assert pm.get_mode() == "secure"

def test_strict_explicit_permissive_mode():
    pm = _make_pm({"RUMI_SECURITY_MODE": "strict", "RUMI_PERMISSION_MODE": "permissive"})
    assert pm.get_mode() == "permissive"

def test_strict_explicit_permissive_warning(caplog):
    with caplog.at_level(logging.WARNING):
        _make_pm({"RUMI_SECURITY_MODE": "strict", "RUMI_PERMISSION_MODE": "permissive"})
    assert any(
        "RUMI_SECURITY_MODE=strict" in r.message and "RUMI_PERMISSION_MODE=permissive" in r.message
        for r in caplog.records
    )

def test_permissive_security_defaults_to_permissive():
    pm = _make_pm({"RUMI_SECURITY_MODE": "permissive"})
    assert pm.get_mode() == "permissive"

def test_both_unset_defaults_to_secure():
    pm = _make_pm({})
    assert pm.get_mode() == "secure"

def test_secure_mode_denies_by_default():
    pm = _make_pm({"RUMI_SECURITY_MODE": "strict"})
    assert pm.get_mode() == "secure"
    assert pm.has_permission("test:tool:foo", "file_read") is False

def test_permissive_mode_allows_all():
    pm = _make_pm({"RUMI_SECURITY_MODE": "permissive"})
    assert pm.get_mode() == "permissive"
    assert pm.has_permission("test:tool:foo", "file_read") is True

def test_init_self_contained():
    pm = _make_pm({})
    assert pm.get_mode() in ("secure", "permissive")
    assert pm.get_mode() == "secure"

def test_mode_arg_overrides_env():
    clean = {k: v for k, v in os.environ.items() if k not in _LINKED_VARS}
    clean["RUMI_SECURITY_MODE"] = "strict"
    with patch.dict(os.environ, clean, clear=True):
        pm = PermissionManager(mode="permissive")
    assert pm.get_mode() == "permissive"

def test_strict_permissive_also_emits_generic_warning(caplog):
    with caplog.at_level(logging.WARNING):
        _make_pm({"RUMI_SECURITY_MODE": "strict", "RUMI_PERMISSION_MODE": "permissive"})
    assert any("PERMISSIVE mode" in r.message for r in caplog.records)
