"""
conftest.py - テスト共通 fixture

core_runtime/__init__.py は大量のサブモジュールを import するため、
テストでは __init__.py の実行を回避し、対象サブモジュールのみを
直接 import できるようにする。
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# core_runtime パッケージを __init__.py を実行せずに登録する
# ---------------------------------------------------------------------------
_CORE_RUNTIME_DIR = str(Path(__file__).resolve().parent.parent / "core_runtime")

if "core_runtime" not in sys.modules:
    _pkg = types.ModuleType("core_runtime")
    _pkg.__path__ = [_CORE_RUNTIME_DIR]
    _pkg.__package__ = "core_runtime"
    _pkg.__file__ = _CORE_RUNTIME_DIR + "/__init__.py"
    sys.modules["core_runtime"] = _pkg

# ---------------------------------------------------------------------------
# 共通 fixture
# ---------------------------------------------------------------------------
import os
import pytest


@pytest.fixture(autouse=True)
def _clean_env_vars(monkeypatch):
    """テスト間で環境変数が漏れないようにする"""
    for var in (
        "RUMI_HMAC_ROTATE",
        "RUMI_HMAC_SECRET",
        "RUMI_LOCAL_PACK_MODE",
        "RUMI_HASH_CACHE_TTL_SEC",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """各テスト後にグローバルシングルトンをリセットする"""
    yield
    # hmac_key_manager
    try:
        from core_runtime import hmac_key_manager as _hkm
        _hkm._global_hmac_key_manager = None
    except Exception:
        pass
    # capability_trust_store
    try:
        from core_runtime import capability_trust_store as _cts
        _cts._global_trust_store = None
    except Exception:
        pass
    # store_registry
    try:
        from core_runtime import store_registry as _sr
        _sr._global_store_registry = None
    except Exception:
        pass
    # vocab_registry
    try:
        from core_runtime import vocab_registry as _vr
        _vr._global_vocab_registry = None
    except Exception:
        pass
    # approval_manager
    try:
        from core_runtime import approval_manager as _am
        _am._global_approval_manager = None
    except Exception:
        pass
