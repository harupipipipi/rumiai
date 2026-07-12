"""
W19-D: host_execution guard テスト

validate_host_execution() の単体テスト。
"""
import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# core_runtime パッケージのモック注入
#   pack_validator.py は from .paths import ... を行うため、
#   テスト環境では core_runtime.paths をモック化してインポートする。
# ---------------------------------------------------------------------------
_cr_key = "core_runtime"
_paths_key = "core_runtime.paths"

if _cr_key not in sys.modules:
    _cr_mod = types.ModuleType(_cr_key)
    _cr_mod.__path__ = ["core_runtime"]
    sys.modules[_cr_key] = _cr_mod

if _paths_key not in sys.modules:
    sys.modules[_paths_key] = MagicMock()

from core_runtime.pack_validator import validate_host_execution_single as validate_host_execution  # noqa: E402

import os
import pytest


# ======================================================================
# テストケース
# ======================================================================


class TestValidateHostExecution:
    """validate_host_execution の単体テスト群"""

    def test_host_exec_true_env_unset(self, monkeypatch):
        """host_execution: true + RUMI_ALLOW_HOST_EXECUTION 未設定 → 拒否"""
        monkeypatch.delenv("RUMI_ALLOW_HOST_EXECUTION", raising=False)
        config = {"host_execution": True}
        ok, msg = validate_host_execution(config)
        assert ok is False
        assert "host_execution requires RUMI_ALLOW_HOST_EXECUTION=true" in msg

    def test_host_exec_true_env_true(self, monkeypatch):
        """host_execution: true + RUMI_ALLOW_HOST_EXECUTION=true → 許可 + WARNING"""
        monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
        config = {"host_execution": True}
        ok, msg = validate_host_execution(config)
        assert ok is True
        assert "WARNING" in msg
        assert "host_execution enabled" in msg

    def test_host_exec_true_env_false(self, monkeypatch):
        """host_execution: true + RUMI_ALLOW_HOST_EXECUTION=false → 拒否"""
        monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "false")
        config = {"host_execution": True}
        ok, msg = validate_host_execution(config)
        assert ok is False
        assert "host_execution requires RUMI_ALLOW_HOST_EXECUTION=true" in msg

    def test_host_exec_false(self, monkeypatch):
        """host_execution: false → 許可、メッセージなし"""
        monkeypatch.delenv("RUMI_ALLOW_HOST_EXECUTION", raising=False)
        config = {"host_execution": False}
        ok, msg = validate_host_execution(config)
        assert ok is True
        assert msg == ""

    def test_host_exec_missing(self, monkeypatch):
        """host_execution フィールドなし → 許可、メッセージなし"""
        monkeypatch.delenv("RUMI_ALLOW_HOST_EXECUTION", raising=False)
        config = {"pack_id": "example_pack"}
        ok, msg = validate_host_execution(config)
        assert ok is True
        assert msg == ""

    def test_multiple_packs_mixed(self, monkeypatch):
        """複数 Pack で host_execution 混在時: 1つでも拒否されたら検出できる"""
        monkeypatch.delenv("RUMI_ALLOW_HOST_EXECUTION", raising=False)
        packs = [
            {"pack_id": "safe_pack", "host_execution": False},
            {"pack_id": "host_pack", "host_execution": True},
            {"pack_id": "normal_pack"},
        ]
        blocked = []
        for cfg in packs:
            ok, msg = validate_host_execution(cfg)
            if not ok:
                blocked.append((cfg.get("pack_id", "?"), msg))
        assert len(blocked) == 1
        assert blocked[0][0] == "host_pack"
        assert "RUMI_ALLOW_HOST_EXECUTION" in blocked[0][1]

    def test_host_exec_true_env_empty_string(self, monkeypatch):
        """host_execution: true + RUMI_ALLOW_HOST_EXECUTION='' → 拒否"""
        monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "")
        config = {"host_execution": True}
        ok, msg = validate_host_execution(config)
        assert ok is False

    def test_host_exec_true_env_uppercase_true(self, monkeypatch):
        """host_execution: true + RUMI_ALLOW_HOST_EXECUTION=TRUE → 拒否(小文字のみ許可)"""
        monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "TRUE")
        config = {"host_execution": True}
        ok, msg = validate_host_execution(config)
        assert ok is False
        assert "RUMI_ALLOW_HOST_EXECUTION" in msg
