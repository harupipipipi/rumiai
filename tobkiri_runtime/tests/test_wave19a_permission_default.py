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


_LINKED_VARS = (
    "RUMI_SECURITY_MODE",
    "RUMI_PERMISSION_MODE",
    "TOBKIRI_PERMISSION_MODE",
    "RUMI_ENVIRONMENT",
)


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
    assert pm.get_mode() == "secure"

def test_strict_explicit_permissive_warning(caplog):
    with caplog.at_level(logging.WARNING):
        _make_pm({"RUMI_SECURITY_MODE": "strict", "RUMI_PERMISSION_MODE": "permissive"})
    assert any(
        "requested permissive permissions" in r.message and "keeping secure" in r.message
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

def test_mode_arg_can_make_permissive_security_stricter():
    clean = {k: v for k, v in os.environ.items() if k not in _LINKED_VARS}
    clean.update({"RUMI_SECURITY_MODE": "permissive", "RUMI_PERMISSION_MODE": "permissive"})
    with patch.dict(os.environ, clean, clear=True):
        pm = PermissionManager(mode="secure")
    assert pm.get_mode() == "secure"

def test_strict_permissive_does_not_claim_effective_permissive_mode(caplog):
    with caplog.at_level(logging.WARNING):
        _make_pm({"RUMI_SECURITY_MODE": "strict", "RUMI_PERMISSION_MODE": "permissive"})
    assert not any("running in PERMISSIVE mode" in r.message for r in caplog.records)


def test_constructor_and_set_mode_cannot_weaken_strict_security(caplog):
    clean = {k: v for k, v in os.environ.items() if k not in _LINKED_VARS}
    clean["RUMI_SECURITY_MODE"] = "strict"
    with patch.dict(os.environ, clean, clear=True), caplog.at_level(logging.WARNING):
        pm = PermissionManager(mode="permissive")
        pm.set_mode("permissive")
    assert pm.get_mode() == "secure"
    assert sum("requested permissive permissions" in record.message for record in caplog.records) == 2


@pytest.mark.parametrize("value", ["", "SECURE-ish", "unknown", 42])
def test_invalid_permission_modes_fail_closed(value, caplog):
    clean = {k: v for k, v in os.environ.items() if k not in _LINKED_VARS}
    clean["RUMI_SECURITY_MODE"] = "permissive"
    with patch.dict(os.environ, clean, clear=True), caplog.at_level(logging.WARNING):
        pm = PermissionManager(mode=value)
        assert pm.get_mode() == "secure"
        pm.set_mode(value)
    assert pm.get_mode() == "secure"
    assert any("failing closed" in record.message for record in caplog.records)


def test_tobkiri_permission_mode_alias_is_supported():
    pm = _make_pm({"RUMI_SECURITY_MODE": "permissive", "TOBKIRI_PERMISSION_MODE": "secure"})
    assert pm.get_mode() == "secure"


def test_tobkiri_permission_mode_alias_can_select_permissive_below_permissive_security():
    pm = _make_pm(
        {
            "RUMI_SECURITY_MODE": "permissive",
            "TOBKIRI_PERMISSION_MODE": "permissive",
        }
    )
    assert pm.get_mode() == "permissive"


def test_matching_legacy_and_tobkiri_modes_are_accepted():
    pm = _make_pm(
        {
            "RUMI_SECURITY_MODE": "permissive",
            "TOBKIRI_PERMISSION_MODE": "permissive",
            "RUMI_PERMISSION_MODE": "permissive",
        }
    )
    assert pm.get_mode() == "permissive"


def test_invalid_environment_permission_mode_fails_closed(caplog):
    with caplog.at_level(logging.WARNING):
        pm = _make_pm(
            {
                "RUMI_SECURITY_MODE": "permissive",
                "RUMI_PERMISSION_MODE": "unknown",
            }
        )
    assert pm.get_mode() == "secure"
    assert any("failing closed" in record.message for record in caplog.records)


def test_conflicting_legacy_and_tobkiri_modes_fail_closed(caplog):
    with caplog.at_level(logging.WARNING):
        pm = _make_pm(
            {
                "RUMI_SECURITY_MODE": "permissive",
                "TOBKIRI_PERMISSION_MODE": "permissive",
                "RUMI_PERMISSION_MODE": "secure",
            }
        )
    assert pm.get_mode() == "secure"
    assert any("conflict" in record.message for record in caplog.records)


def test_production_clamps_permissive_security_and_permission_mode():
    pm = _make_pm(
        {
            "RUMI_SECURITY_MODE": "permissive",
            "RUMI_PERMISSION_MODE": "permissive",
            "RUMI_ENVIRONMENT": "production",
        }
    )
    assert pm.get_mode() == "secure"
