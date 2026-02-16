"""
test_kernel_context.py - KernelContextBuilder のユニットテスト

M-7: Null 下流防御の検証を含む
"""

import pytest

from core_runtime.kernel_context_builder import (
    KernelContextBuilder,
    NullService,
)


class FakeDiagnostics:
    def record_step(self, **kwargs):
        pass
    def as_dict(self):
        return {}


class FakeInstallJournal:
    def set_interface_registry(self, ir):
        pass


class FakeInterfaceRegistry:
    pass


class FakeEventBus:
    pass


class FakeLifecycle:
    pass


class TestNullService:
    """NullService の振る舞いテスト"""

    def test_bool_is_false(self):
        ns = NullService("test")
        assert not ns
        assert bool(ns) is False

    def test_repr(self):
        ns = NullService("mount_manager")
        assert "mount_manager" in repr(ns)

    def test_attribute_access_returns_callable(self):
        ns = NullService("test")
        result = ns.some_method
        assert callable(result)

    def test_method_call_returns_none(self):
        ns = NullService("test")
        assert ns.some_method() is None
        assert ns.another_method("arg1", key="val") is None

    def test_direct_call_returns_none(self):
        ns = NullService("test")
        assert ns() is None

    def test_chained_access(self):
        """下流で .get_something().do_something() のようなチェーンでも壊れないこと"""
        ns = NullService("test")
        result = ns.get_manager
        assert result() is None

    def test_internal_attributes_raise(self):
        """_ で始まる属性は AttributeError を起こすべき"""
        ns = NullService("test")
        with pytest.raises(AttributeError):
            _ = ns._internal


class TestKernelContextBuilder:
    """KernelContextBuilder のテスト"""

    def _make_builder(self):
        return KernelContextBuilder(
            diagnostics=FakeDiagnostics(),
            install_journal=FakeInstallJournal(),
            interface_registry=FakeInterfaceRegistry(),
            event_bus=FakeEventBus(),
            lifecycle=FakeLifecycle(),
        )

    def test_build_returns_dict(self):
        builder = self._make_builder()
        ctx = builder.build()
        assert isinstance(ctx, dict)

    def test_core_services_always_present(self):
        builder = self._make_builder()
        ctx = builder.build()
        assert "diagnostics" in ctx
        assert "install_journal" in ctx
        assert "interface_registry" in ctx
        assert "event_bus" in ctx
        assert "lifecycle" in ctx

    def test_disabled_targets_initialized(self):
        builder = self._make_builder()
        ctx = builder.build()
        assert "_disabled_targets" in ctx
        assert "packs" in ctx["_disabled_targets"]
        assert "components" in ctx["_disabled_targets"]

    def test_m7_null_safety_mount_manager(self):
        """M-7: mount_manager が取得できなくても NullService になること"""
        builder = self._make_builder()
        ctx = builder.build()
        mm = ctx["mount_manager"]
        result = mm.get_mount("test")
        assert result is None

    def test_m7_null_safety_registry(self):
        """M-7: registry が NullService でも壊れないこと"""
        builder = self._make_builder()
        ctx = builder.build()
        reg = ctx["registry"]
        result = reg.get_all_components()
        assert result is None

    def test_m7_null_safety_active_ecosystem(self):
        """M-7: active_ecosystem が NullService でも壊れないこと"""
        builder = self._make_builder()
        ctx = builder.build()
        ae = ctx["active_ecosystem"]
        result = ae.get_all_overrides()
        assert result is None

    def test_m7_services_are_not_none(self):
        """M-7: サービスが None ではなく NullService であること"""
        builder = self._make_builder()
        ctx = builder.build()
        for key in ["mount_manager", "registry", "active_ecosystem"]:
            assert ctx[key] is not None
