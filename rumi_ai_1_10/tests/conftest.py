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
    # ================================================================
    # DI Container (must be first — clears all DI-managed singletons)
    # ================================================================
    try:
        from core_runtime.di_container import reset_container
        reset_container()
    except Exception:
        pass

    # ================================================================
    # Legacy global variables (cleared for safety, not yet removed)
    # ================================================================

    # network_grant_manager
    try:
        from core_runtime import network_grant_manager as _ngm
        if hasattr(_ngm, '_global_network_grant_manager'):
            _ngm._global_network_grant_manager = None
    except Exception:
        pass
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
        if hasattr(_sr, '_global_store_registry'):
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
    # permission_manager
    try:
        from core_runtime import permission_manager as _pm
        _pm._global_permission_manager = None
    except Exception:
        pass
    # container_orchestrator
    try:
        from core_runtime import container_orchestrator as _co
        if hasattr(_co, '_global_orchestrator'):
            _co._global_orchestrator = None
    except Exception:
        pass
    # host_privilege_manager
    try:
        from core_runtime import host_privilege_manager as _hpm
        if hasattr(_hpm, '_global_privilege_manager'):
            _hpm._global_privilege_manager = None
    except Exception:
        pass
    # flow_composer
    try:
        from core_runtime import flow_composer as _fc
        if hasattr(_fc, '_global_flow_composer'):
            _fc._global_flow_composer = None
    except Exception:
        pass
    # function_alias_registry
    try:
        from core_runtime import function_alias as _fa
        if hasattr(_fa, '_global_function_alias_registry'):
            _fa._global_function_alias_registry = None
    except Exception:
        pass
    # secrets_store
    try:
        from core_runtime import secrets_store as _ss
        if hasattr(_ss, '_global_secrets_store'):
            _ss._global_secrets_store = None
    except Exception:
        pass
    # modifier_loader / modifier_applier
    try:
        from core_runtime import flow_modifier as _fm
        if hasattr(_fm, '_global_modifier_loader'):
            _fm._global_modifier_loader = None
        if hasattr(_fm, '_global_modifier_applier'):
            _fm._global_modifier_applier = None
    except Exception:
        pass

    # ================================================================
    # Wave 5: New DI-managed services (legacy globals cleared)
    # ================================================================

    # pack_api_server
    try:
        from core_runtime import pack_api_server as _pas
        if hasattr(_pas, '_api_server'):
            _pas._api_server = None
    except Exception:
        pass
    # egress_proxy (UDS proxy manager)
    try:
        from core_runtime import egress_proxy as _ep
        if hasattr(_ep, '_global_uds_proxy_manager'):
            _ep._global_uds_proxy_manager = None
        if hasattr(_ep, '_global_egress_proxy'):
            _ep._global_egress_proxy = None
    except Exception:
        pass
    # python_file_executor
    try:
        from core_runtime import python_file_executor as _pfe
        if hasattr(_pfe, '_global_executor'):
            _pfe._global_executor = None
    except Exception:
        pass
    # secure_executor
    try:
        from core_runtime import secure_executor as _se
        if hasattr(_se, '_global_secure_executor'):
            _se._global_secure_executor = None
    except Exception:
        pass
    # lib_executor
    try:
        from core_runtime import lib_executor as _le
        if hasattr(_le, '_global_lib_executor'):
            _le._global_lib_executor = None
    except Exception:
        pass
    # unit_executor
    try:
        from core_runtime import unit_executor as _ue
        if hasattr(_ue, '_global_unit_executor'):
            _ue._global_unit_executor = None
    except Exception:
        pass
    # capability_executor
    try:
        from core_runtime import capability_executor as _ce
        if hasattr(_ce, '_global_executor'):
            _ce._global_executor = None
    except Exception:
        pass
