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


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------
_LINKED_VARS = ("RUMI_SECURITY_MODE", "RUMI_PERMISSION_MODE")


def _make_pm(env: dict) -> PermissionManager:
    """指定した環境変数のみが存在する状態で PermissionManager を生成する。"""
    clean = {k: v for k, v in os.environ.items() if k not in _LINKED_VARS}
    clean.update(env)
    with patch.dict(os.environ, clean, clear=True):
        return PermissionManager()


# ===========================================================================
# T1: SECURITY_MODE=strict + PERMISSION_MODE 未設定 → secure
# ===========================================================================
def test_strict_no_perm_mode_defaults_to_secure():
    pm = _make_pm({"RUMI_SECURITY_MODE": "strict"})
    assert pm.get_mode() == "secure"


# ===========================================================================
# T2: SECURITY_MODE=strict + PERMISSION_MODE=secure → secure
# ===========================================================================
def test_strict_explicit_secure():
    pm = _make_pm({
        "RUMI_SECURITY_MODE": "strict",
        "RUMI_PERMISSION_MODE": "secure",
    })
    assert pm.get_mode() == "secure"


# ===========================================================================
# T3: SECURITY_MODE=strict + PERMISSION_MODE=permissive → permissive + WARNING
# ===========================================================================
def test_strict_explicit_permissive_mode():
    pm = _make_pm({
        "RUMI_SECURITY_MODE": "strict",
        "RUMI_PERMISSION_MODE": "permissive",
    })
    assert pm.get_mode() == "permissive"


def test_strict_explicit_permissive_warning(caplog):
    with caplog.at_level(logging.WARNING):
        _make_pm({
            "RUMI_SECURITY_MODE": "strict",
            "RUMI_PERMISSION_MODE": "permissive",
        })
    assert any(
        "RUMI_SECURITY_MODE=strict" in r.message
        and "RUMI_PERMISSION_MODE=permissive" in r.message
        for r in caplog.records
    ), f"Expected linked-warning not found. Records: {[r.message for r in caplog.records]}"


# ===========================================================================
# T4: SECURITY_MODE=permissive + PERMISSION_MODE 未設定 → permissive
# ===========================================================================
def test_permissive_security_defaults_to_permissive():
    pm = _make_pm({"RUMI_SECURITY_MODE": "permissive"})
    assert pm.get_mode() == "permissive"


# ===========================================================================
# T5: 両方未設定 → strict がデフォルト → secure
# ===========================================================================
def test_both_unset_defaults_to_secure():
    pm = _make_pm({})
    assert pm.get_mode() == "secure"


# ===========================================================================
# T6: secure モードで has_permission() が権限なしなら False
# ===========================================================================
def test_secure_mode_denies_by_default():
    pm = _make_pm({"RUMI_SECURITY_MODE": "strict"})
    assert pm.get_mode() == "secure"
    assert pm.has_permission("test:tool:foo", "file_read") is False


# ===========================================================================
# T7: permissive モードで has_permission() が True
# ===========================================================================
def test_permissive_mode_allows_all():
    pm = _make_pm({"RUMI_SECURITY_MODE": "permissive"})
    assert pm.get_mode() == "permissive"
    assert pm.has_permission("test:tool:foo", "file_read") is True


# ===========================================================================
# T8: 連動ロジックが __init__() 内で完結（外部初期化に依存しない）
# ===========================================================================
def test_init_self_contained():
    pm = _make_pm({})
    # __init__ 完了時点でモードが確定している
    assert pm.get_mode() in ("secure", "permissive")
    assert pm.get_mode() == "secure"


# ===========================================================================
# T9: mode 引数が明示されていれば環境変数に関係なくそのまま使う
# ===========================================================================
def test_mode_arg_overrides_env():
    clean = {k: v for k, v in os.environ.items() if k not in _LINKED_VARS}
    clean["RUMI_SECURITY_MODE"] = "strict"
    with patch.dict(os.environ, clean, clear=True):
        pm = PermissionManager(mode="permissive")
    assert pm.get_mode() == "permissive"


# ===========================================================================
# T10: strict + permissive 明示時に既存 permissive WARNING も出力される
# ===========================================================================
def test_strict_permissive_also_emits_generic_warning(caplog):
    with caplog.at_level(logging.WARNING):
        _make_pm({
            "RUMI_SECURITY_MODE": "strict",
            "RUMI_PERMISSION_MODE": "permissive",
        })
    assert any(
        "PERMISSIVE mode" in r.message for r in caplog.records
    ), f"Expected generic permissive warning not found. Records: {[r.message for r in caplog.records]}"
