"""
test_wave15e_di_container.py - Wave 15-E DI コンテナ基盤サービス登録テスト

テスト対象:
  - Wave 15 で追加した 3 サービス (health_checker, metrics_collector, profiler)
    が get_container() で取得できること
  - キャッシュが効くこと（2回目 get で同一インスタンス）
  - reset 後に新インスタンスが生成されること
  - 既存サービスが壊れていないこと
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# ダミーモジュール登録 — 動的インポートを安全にする
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
from rumi_ai_1_10.core_runtime.health import HealthChecker  # noqa: E402
from rumi_ai_1_10.core_runtime.metrics import MetricsCollector  # noqa: E402
from rumi_ai_1_10.core_runtime.profiling import Profiler  # noqa: E402


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
# Wave 15 サービス登録テスト
# ======================================================================

class TestWave15Registration:
    """Wave 15 で追加された 3 サービスが DI コンテナに登録されていること"""

    def test_health_checker_registered(self):
        c = get_container()
        assert c.has("health_checker")

    def test_metrics_collector_registered(self):
        c = get_container()
        assert c.has("metrics_collector")

    def test_profiler_registered(self):
        c = get_container()
        assert c.has("profiler")


# ======================================================================
# Wave 15 サービス取得テスト
# ======================================================================

class TestWave15Get:
    """Wave 15 サービスが正しい型のインスタンスとして取得できること"""

    def test_get_health_checker(self):
        c = get_container()
        obj = c.get("health_checker")
        assert isinstance(obj, HealthChecker)

    def test_get_metrics_collector(self):
        c = get_container()
        obj = c.get("metrics_collector")
        assert isinstance(obj, MetricsCollector)

    def test_get_profiler(self):
        c = get_container()
        obj = c.get("profiler")
        assert isinstance(obj, Profiler)

    def test_get_or_none_health_checker(self):
        c = get_container()
        obj = c.get_or_none("health_checker")
        assert isinstance(obj, HealthChecker)

    def test_get_or_none_metrics_collector(self):
        c = get_container()
        obj = c.get_or_none("metrics_collector")
        assert isinstance(obj, MetricsCollector)

    def test_get_or_none_profiler(self):
        c = get_container()
        obj = c.get_or_none("profiler")
        assert isinstance(obj, Profiler)


# ======================================================================
# キャッシュテスト
# ======================================================================

class TestWave15Cache:
    """DI コンテナのキャッシュ動作確認: 2回目 get で同一インスタンス"""

    def test_health_checker_cached(self):
        c = get_container()
        obj1 = c.get("health_checker")
        obj2 = c.get("health_checker")
        assert obj1 is obj2

    def test_metrics_collector_cached(self):
        c = get_container()
        obj1 = c.get("metrics_collector")
        obj2 = c.get("metrics_collector")
        assert obj1 is obj2

    def test_profiler_cached(self):
        c = get_container()
        obj1 = c.get("profiler")
        obj2 = c.get("profiler")
        assert obj1 is obj2


# ======================================================================
# リセットテスト
# ======================================================================

class TestWave15Reset:
    """reset 後に新しいインスタンスが生成されること"""

    def test_reset_health_checker(self):
        c = get_container()
        obj1 = c.get("health_checker")
        c.reset("health_checker")
        obj2 = c.get("health_checker")
        assert obj1 is not obj2
        assert isinstance(obj2, HealthChecker)

    def test_reset_metrics_collector(self):
        c = get_container()
        obj1 = c.get("metrics_collector")
        c.reset("metrics_collector")
        obj2 = c.get("metrics_collector")
        assert obj1 is not obj2
        assert isinstance(obj2, MetricsCollector)

    def test_reset_profiler(self):
        c = get_container()
        obj1 = c.get("profiler")
        c.reset("profiler")
        obj2 = c.get("profiler")
        assert obj1 is not obj2
        assert isinstance(obj2, Profiler)

    def test_reset_container_recreates_all(self):
        c1 = get_container()
        hc1 = c1.get("health_checker")
        mc1 = c1.get("metrics_collector")
        pf1 = c1.get("profiler")
        reset_container()
        c2 = get_container()
        hc2 = c2.get("health_checker")
        mc2 = c2.get("metrics_collector")
        pf2 = c2.get("profiler")
        assert hc1 is not hc2
        assert mc1 is not mc2
        assert pf1 is not pf2


# ======================================================================
# 既存サービス互換性テスト
# ======================================================================

class TestExistingServicesNotBroken:
    """Wave 15 追加後も既存サービスが registered_names に含まれること"""

    def test_audit_logger_in_registered_names(self):
        c = get_container()
        names = c.registered_names()
        assert "audit_logger" in names

    def test_diagnostics_in_registered_names(self):
        c = get_container()
        names = c.registered_names()
        assert "diagnostics" in names

    def test_install_journal_in_registered_names(self):
        c = get_container()
        names = c.registered_names()
        assert "install_journal" in names

    def test_event_bus_in_registered_names(self):
        c = get_container()
        names = c.registered_names()
        assert "event_bus" in names

    def test_wave15_services_in_registered_names(self):
        c = get_container()
        names = c.registered_names()
        assert "health_checker" in names
        assert "metrics_collector" in names
        assert "profiler" in names

    def test_total_service_count_at_least_28(self):
        """Wave 1-8 で 25 + Wave 15 で 3 = 少なくとも 28 サービス"""
        c = get_container()
        names = c.registered_names()
        assert len(names) >= 28


# ======================================================================
# DI 取得後の基本機能テスト
# ======================================================================

class TestWave15Functionality:
    """DI 経由で取得したインスタンスが正常に動作すること"""

    def test_health_checker_has_aggregate_health(self):
        c = get_container()
        hc = c.get("health_checker")
        result = hc.aggregate_health()
        assert result["status"] == "UP"
        assert "probes" in result
        assert "timestamp" in result

    def test_metrics_collector_has_increment(self):
        c = get_container()
        mc = c.get("metrics_collector")
        mc.increment("test_counter")
        snap = mc.snapshot()
        assert "test_counter" in snap["counters"]

    def test_profiler_has_profile(self):
        c = get_container()
        pf = c.get("profiler")
        with pf.profile("test_section"):
            pass
        stats = pf.get_stats("test_section")
        assert stats is not None
        assert stats["count"] == 1
