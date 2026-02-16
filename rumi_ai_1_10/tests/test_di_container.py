"""
test_di_container.py - DIContainer のユニットテスト

対象: core_runtime/di_container.py
"""
from __future__ import annotations

import threading
from typing import Any

import pytest

from core_runtime.di_container import DIContainer, get_container, reset_container


# ===================================================================
# DIContainer 基本動作
# ===================================================================


class TestDIContainerBasic:

    def test_register_and_get(self) -> None:
        c = DIContainer()
        c.register("svc", lambda: {"hello": "world"})
        result = c.get("svc")
        assert result == {"hello": "world"}

    def test_get_returns_cached_instance(self) -> None:
        call_count = 0

        def factory() -> dict:
            nonlocal call_count
            call_count += 1
            return {"n": call_count}

        c = DIContainer()
        c.register("svc", factory)
        first = c.get("svc")
        second = c.get("svc")
        assert first is second
        assert call_count == 1

    def test_get_unregistered_raises_key_error(self) -> None:
        c = DIContainer()
        with pytest.raises(KeyError, match="Service not registered"):
            c.get("nonexistent")

    def test_get_or_none_returns_none_for_unregistered(self) -> None:
        c = DIContainer()
        assert c.get_or_none("nonexistent") is None

    def test_get_or_none_returns_instance(self) -> None:
        c = DIContainer()
        c.register("svc", lambda: 42)
        assert c.get_or_none("svc") == 42

    def test_has(self) -> None:
        c = DIContainer()
        assert c.has("svc") is False
        c.register("svc", lambda: None)
        assert c.has("svc") is True

    def test_registered_names(self) -> None:
        c = DIContainer()
        c.register("a", lambda: 1)
        c.register("b", lambda: 2)
        names = c.registered_names()
        assert sorted(names) == ["a", "b"]

    def test_reset_clears_cached_instance(self) -> None:
        call_count = 0

        def factory() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        c = DIContainer()
        c.register("svc", factory)
        assert c.get("svc") == 1
        c.reset("svc")
        assert c.get("svc") == 2

    def test_reset_all(self) -> None:
        c = DIContainer()
        counters = {"a": 0, "b": 0}

        def make_factory(name: str):
            def factory() -> int:
                counters[name] += 1
                return counters[name]
            return factory

        c.register("a", make_factory("a"))
        c.register("b", make_factory("b"))
        c.get("a")
        c.get("b")
        c.reset_all()
        assert c.get("a") == 2
        assert c.get("b") == 2

    def test_set_instance(self) -> None:
        c = DIContainer()
        c.register("svc", lambda: "from_factory")
        c.set_instance("svc", "from_direct")
        assert c.get("svc") == "from_direct"

    def test_register_overwrites_and_clears_cache(self) -> None:
        c = DIContainer()
        c.register("svc", lambda: "first")
        assert c.get("svc") == "first"
        c.register("svc", lambda: "second")
        assert c.get("svc") == "second"


# ===================================================================
# ファクトリ例外
# ===================================================================


class TestDIContainerFactoryException:

    def test_factory_exception_not_cached(self) -> None:
        call_count = 0

        def flaky_factory() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("first call fails")
            return "success"

        c = DIContainer()
        c.register("svc", flaky_factory)

        with pytest.raises(RuntimeError, match="first call fails"):
            c.get("svc")

        # 2回目は成功するはず（1回目の例外がキャッシュされていない）
        assert c.get("svc") == "success"

    def test_get_or_none_returns_none_on_factory_exception(self) -> None:
        c = DIContainer()

        def failing_factory() -> None:
            raise ValueError("boom")

        c.register("svc", failing_factory)
        assert c.get_or_none("svc") is None


# ===================================================================
# スレッドセーフ
# ===================================================================


class TestDIContainerThreadSafety:

    def test_concurrent_get_returns_same_instance(self) -> None:
        c = DIContainer()
        c.register("svc", lambda: object())

        results: list = []
        errors: list = []

        def worker() -> None:
            try:
                results.append(c.get("svc"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 20
        # 全て同一インスタンス
        assert all(r is results[0] for r in results)


# ===================================================================
# register_defaults テスト
# ===================================================================


class TestRegisterDefaults:

    def test_defaults_registered(self) -> None:
        container = get_container()
        assert container.has("audit_logger")
        assert container.has("hmac_key_manager")
        assert container.has("vocab_registry")

    def test_audit_logger_default_factory(self, tmp_path) -> None:
        from core_runtime.audit_logger import AuditLogger
        container = get_container()
        instance = container.get("audit_logger")
        assert isinstance(instance, AuditLogger)

    def test_vocab_registry_default_factory(self) -> None:
        from core_runtime.vocab_registry import VocabRegistry
        container = get_container()
        instance = container.get("vocab_registry")
        assert isinstance(instance, VocabRegistry)


# ===================================================================
# 後方互換テスト
# ===================================================================


class TestBackwardCompatibility:

    def test_get_audit_logger_returns_di_instance(self, tmp_path) -> None:
        from core_runtime.audit_logger import get_audit_logger
        container = get_container()
        di_instance = container.get("audit_logger")
        func_instance = get_audit_logger()
        assert di_instance is func_instance

    def test_get_vocab_registry_returns_di_instance(self) -> None:
        from core_runtime.vocab_registry import get_vocab_registry
        container = get_container()
        di_instance = container.get("vocab_registry")
        func_instance = get_vocab_registry()
        assert di_instance is func_instance

    def test_reset_audit_logger_updates_di(self, tmp_path) -> None:
        from core_runtime.audit_logger import get_audit_logger, reset_audit_logger
        old = get_audit_logger()
        new = reset_audit_logger(str(tmp_path / "audit"))
        assert old is not new
        assert get_audit_logger() is new
        assert get_container().get("audit_logger") is new

    def test_reset_vocab_registry_updates_di(self) -> None:
        from core_runtime.vocab_registry import get_vocab_registry, reset_vocab_registry
        old = get_vocab_registry()
        new = reset_vocab_registry()
        assert old is not new
        assert get_vocab_registry() is new
        assert get_container().get("vocab_registry") is new


# ===================================================================
# get_container / reset_container
# ===================================================================


class TestGlobalContainer:

    def test_get_container_returns_same_instance(self) -> None:
        c1 = get_container()
        c2 = get_container()
        assert c1 is c2

    def test_reset_container_creates_new(self) -> None:
        c1 = get_container()
        reset_container()
        c2 = get_container()
        assert c1 is not c2

    def test_reset_container_registers_defaults(self) -> None:
        reset_container()
        c = get_container()
        assert c.has("audit_logger")
        assert c.has("hmac_key_manager")
        assert c.has("vocab_registry")
