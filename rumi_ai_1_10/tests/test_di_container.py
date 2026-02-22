"""
test_di_container.py - DI コンテナ Wave 8 テスト (T-039)

テスト対象:
  - Wave 8 で追加した 5 サービスが get_container() で取得できること
  - reset_container() 後に再取得できること
  - Kernel をデフォルト引数で生成し DI 経由のインスタンスであること
  - Kernel に明示的に引数を渡した場合、渡したものが使われること
  - 後方互換: Kernel(diagnostics=Diagnostics()) が正常に動作すること
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# ダミーモジュール登録 — Kernel 初期化時の動的インポートを安全にする
# ---------------------------------------------------------------------------
for _mod_name in [
    "backend_core",
    "backend_core.ecosystem",
    "backend_core.ecosystem.registry",
    "backend_core.ecosystem.active_ecosystem",
    "backend_core.ecosystem.mounts",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)

# pack_api_server ダミー
_dummy_pack_api = types.ModuleType("rumi_ai_1_10.core_runtime.pack_api_server")


class _APIResponse:
    def __init__(self, success, data=None, error=None):
        self.success = success
        self.data = data
        self.error = error


_dummy_pack_api.APIResponse = _APIResponse
sys.modules.setdefault("rumi_ai_1_10.core_runtime.pack_api_server", _dummy_pack_api)

# audit_logger ダミー
_dummy_audit = types.ModuleType("rumi_ai_1_10.core_runtime.audit_logger")
_dummy_audit.get_audit_logger = MagicMock(return_value=MagicMock())
sys.modules.setdefault("rumi_ai_1_10.core_runtime.audit_logger", _dummy_audit)

# ---------------------------------------------------------------------------
# テスト対象インポート
# ---------------------------------------------------------------------------
from rumi_ai_1_10.core_runtime.di_container import (  # noqa: E402
    DIContainer,
    get_container,
    reset_container,
)
from rumi_ai_1_10.core_runtime.diagnostics import Diagnostics  # noqa: E402
from rumi_ai_1_10.core_runtime.install_journal import InstallJournal  # noqa: E402
from rumi_ai_1_10.core_runtime.interface_registry import InterfaceRegistry  # noqa: E402
from rumi_ai_1_10.core_runtime.event_bus import EventBus  # noqa: E402
from rumi_ai_1_10.core_runtime.component_lifecycle import ComponentLifecycleExecutor  # noqa: E402


# ======================================================================
# Fixture
# ======================================================================

@pytest.fixture(autouse=True)
def _reset_di():
    """各テストの前後で DI コンテナをリセット"""
    reset_container()
    yield
    reset_container()


# ======================================================================
# Wave 8 サービス登録テスト
# ======================================================================

class TestWave8Registration:
    """Wave 8 で追加された 5 サービスが DI コンテナに登録されていること"""

    def test_diagnostics_registered(self):
        c = get_container()
        assert c.has("diagnostics")

    def test_install_journal_registered(self):
        c = get_container()
        assert c.has("install_journal")

    def test_interface_registry_registered(self):
        c = get_container()
        assert c.has("interface_registry")

    def test_event_bus_registered(self):
        c = get_container()
        assert c.has("event_bus")

    def test_component_lifecycle_registered(self):
        c = get_container()
        assert c.has("component_lifecycle")


# ======================================================================
# Wave 8 サービス取得テスト
# ======================================================================

class TestWave8Get:
    """Wave 8 サービスが正しい型のインスタンスとして取得できること"""

    def test_get_diagnostics(self):
        c = get_container()
        obj = c.get("diagnostics")
        assert isinstance(obj, Diagnostics)

    def test_get_install_journal(self):
        c = get_container()
        obj = c.get("install_journal")
        assert isinstance(obj, InstallJournal)

    def test_get_interface_registry(self):
        c = get_container()
        obj = c.get("interface_registry")
        assert isinstance(obj, InterfaceRegistry)

    def test_get_event_bus(self):
        c = get_container()
        obj = c.get("event_bus")
        assert isinstance(obj, EventBus)

    def test_get_component_lifecycle(self):
        c = get_container()
        obj = c.get("component_lifecycle")
        assert isinstance(obj, ComponentLifecycleExecutor)

    def test_component_lifecycle_has_diagnostics(self):
        """component_lifecycle の diagnostics が DI 経由で設定されていること"""
        c = get_container()
        lc = c.get("component_lifecycle")
        diag = c.get("diagnostics")
        assert lc.diagnostics is diag

    def test_component_lifecycle_has_install_journal(self):
        """component_lifecycle の install_journal が DI 経由で設定されていること"""
        c = get_container()
        lc = c.get("component_lifecycle")
        ij = c.get("install_journal")
        assert lc.install_journal is ij


# ======================================================================
# キャッシュ・リセットテスト
# ======================================================================

class TestCacheAndReset:
    """DI コンテナのキャッシュとリセットの動作確認"""

    def test_same_instance_on_repeated_get(self):
        c = get_container()
        d1 = c.get("diagnostics")
        d2 = c.get("diagnostics")
        assert d1 is d2

    def test_reset_container_creates_new_instances(self):
        c1 = get_container()
        d1 = c1.get("diagnostics")
        reset_container()
        c2 = get_container()
        d2 = c2.get("diagnostics")
        assert d1 is not d2

    def test_reset_single_service(self):
        c = get_container()
        d1 = c.get("diagnostics")
        c.reset("diagnostics")
        d2 = c.get("diagnostics")
        assert d1 is not d2

    def test_reset_all_services(self):
        c = get_container()
        d1 = c.get("diagnostics")
        ij1 = c.get("install_journal")
        c.reset_all()
        d2 = c.get("diagnostics")
        ij2 = c.get("install_journal")
        assert d1 is not d2
        assert ij1 is not ij2


# ======================================================================
# Kernel DI フォールバックテスト
# ======================================================================

class TestKernelDIFallback:
    """Kernel をデフォルト引数で生成した際に DI 経由のインスタンスが使われること"""

    def test_kernel_default_diagnostics_from_di(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        k = KernelCore()
        c = get_container()
        assert isinstance(k.diagnostics, Diagnostics)
        assert k.diagnostics is c.get("diagnostics")

    def test_kernel_default_install_journal_from_di(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        k = KernelCore()
        c = get_container()
        assert isinstance(k.install_journal, InstallJournal)
        assert k.install_journal is c.get("install_journal")

    def test_kernel_default_interface_registry_from_di(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        k = KernelCore()
        c = get_container()
        assert isinstance(k.interface_registry, InterfaceRegistry)
        assert k.interface_registry is c.get("interface_registry")

    def test_kernel_default_event_bus_from_di(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        k = KernelCore()
        c = get_container()
        assert isinstance(k.event_bus, EventBus)
        assert k.event_bus is c.get("event_bus")

    def test_kernel_default_lifecycle_is_valid(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        k = KernelCore()
        assert isinstance(k.lifecycle, ComponentLifecycleExecutor)
        assert k.lifecycle.diagnostics is k.diagnostics
        assert k.lifecycle.install_journal is k.install_journal


# ======================================================================
# Kernel 明示引数テスト（後方互換）
# ======================================================================

class TestKernelExplicitArgs:
    """Kernel に明示的に引数を渡した場合、DI ではなく渡したものが使われること"""

    def test_explicit_diagnostics(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        my_diag = Diagnostics()
        k = KernelCore(diagnostics=my_diag)
        assert k.diagnostics is my_diag
        c = get_container()
        assert k.diagnostics is not c.get("diagnostics")

    def test_explicit_install_journal(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        my_ij = InstallJournal()
        k = KernelCore(install_journal=my_ij)
        assert k.install_journal is my_ij

    def test_explicit_interface_registry(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        my_ir = InterfaceRegistry()
        k = KernelCore(interface_registry=my_ir)
        assert k.interface_registry is my_ir

    def test_explicit_event_bus(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        my_eb = EventBus()
        k = KernelCore(event_bus=my_eb)
        assert k.event_bus is my_eb

    def test_explicit_lifecycle(self):
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        my_diag = Diagnostics()
        my_ij = InstallJournal()
        my_lc = ComponentLifecycleExecutor(diagnostics=my_diag, install_journal=my_ij)
        k = KernelCore(lifecycle=my_lc)
        assert k.lifecycle is my_lc

    def test_explicit_diagnostics_propagates_to_lifecycle(self):
        """明示的に渡した diagnostics が lifecycle にも反映されること"""
        from rumi_ai_1_10.core_runtime.kernel_core import KernelCore
        my_diag = Diagnostics()
        k = KernelCore(diagnostics=my_diag)
        assert k.lifecycle.diagnostics is my_diag

    def test_backward_compat_kernel_class(self):
        """Kernel クラス（kernel.py）経由でも後方互換が維持されること"""
        from rumi_ai_1_10.core_runtime.kernel import Kernel
        my_diag = Diagnostics()
        k = Kernel(diagnostics=my_diag)
        assert k.diagnostics is my_diag
        assert isinstance(k.install_journal, InstallJournal)
        assert isinstance(k.interface_registry, InterfaceRegistry)
        assert isinstance(k.event_bus, EventBus)
        assert isinstance(k.lifecycle, ComponentLifecycleExecutor)
