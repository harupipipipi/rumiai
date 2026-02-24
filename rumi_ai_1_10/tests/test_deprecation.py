"""
test_deprecation.py - deprecation モジュールのテスト (Wave 14 T-057)

DeprecationInfo, DeprecationRegistry, deprecated デコレータ,
deprecated_class デコレータの網羅的なテストを行う。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import warnings
from typing import Any, Dict, List

import pytest

from core_runtime.deprecation import (
    DeprecationInfo,
    DeprecationRegistry,
    _emit_deprecation_warning,
    _get_deprecation_level,
    deprecated,
    deprecated_class,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture(autouse=True)
def _clean_registry():
    """各テスト前後でレジストリをクリーンアップする。"""
    DeprecationRegistry._reset_instance()
    yield
    DeprecationRegistry._reset_instance()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """RUMI_DEPRECATION_LEVEL 環境変数をクリーンにする。"""
    monkeypatch.delenv("RUMI_DEPRECATION_LEVEL", raising=False)


# ======================================================================
# DeprecationInfo データクラス
# ======================================================================

class TestDeprecationInfo:
    """DeprecationInfo データクラスのテスト。"""

    def test_basic_creation(self):
        info = DeprecationInfo(name="old_func", since="1.5", removed_in="2.0")
        assert info.name == "old_func"
        assert info.since == "1.5"
        assert info.removed_in == "2.0"
        assert info.alternative is None

    def test_with_alternative(self):
        info = DeprecationInfo(
            name="old_func", since="1.5", removed_in="2.0",
            alternative="new_func",
        )
        assert info.alternative == "new_func"

    def test_message_without_alternative(self):
        info = DeprecationInfo(name="old_func", since="1.5", removed_in="2.0")
        msg = info.message
        assert "old_func" in msg
        assert "1.5" in msg
        assert "2.0" in msg
        assert "instead" not in msg

    def test_message_with_alternative(self):
        info = DeprecationInfo(
            name="old_func", since="1.5", removed_in="2.0",
            alternative="new_func",
        )
        msg = info.message
        assert "old_func" in msg
        assert "1.5" in msg
        assert "2.0" in msg
        assert "Use new_func instead." in msg

    def test_frozen_immutability(self):
        info = DeprecationInfo(name="old_func", since="1.5", removed_in="2.0")
        with pytest.raises(AttributeError):
            info.name = "other"  # type: ignore[misc]

    def test_to_dict_without_alternative(self):
        info = DeprecationInfo(name="old_func", since="1.5", removed_in="2.0")
        d = info.to_dict()
        assert d == {"name": "old_func", "since": "1.5", "removed_in": "2.0"}
        assert "alternative" not in d

    def test_to_dict_with_alternative(self):
        info = DeprecationInfo(
            name="old_func", since="1.5", removed_in="2.0",
            alternative="new_func",
        )
        d = info.to_dict()
        assert d == {
            "name": "old_func",
            "since": "1.5",
            "removed_in": "2.0",
            "alternative": "new_func",
        }


# ======================================================================
# DeprecationRegistry
# ======================================================================

class TestDeprecationRegistry:
    """DeprecationRegistry シングルトンのテスト。"""

    def test_singleton_identity(self):
        r1 = DeprecationRegistry.get_instance()
        r2 = DeprecationRegistry.get_instance()
        assert r1 is r2

    def test_register_and_get_all(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("old_func", since="1.0", removed_in="2.0")
        all_entries = reg.get_all()
        assert "old_func" in all_entries
        assert all_entries["old_func"].since == "1.0"

    def test_register_multiple(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("func_a", since="1.0", removed_in="2.0")
        reg.register("func_b", since="1.1", removed_in="2.0")
        reg.register("func_c", since="1.2", removed_in="3.0")
        assert len(reg.get_all()) == 3

    def test_register_overwrites_same_name(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("old_func", since="1.0", removed_in="2.0")
        reg.register("old_func", since="1.5", removed_in="3.0")
        all_entries = reg.get_all()
        assert len(all_entries) == 1
        assert all_entries["old_func"].since == "1.5"

    def test_get_all_returns_copy(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("func_a", since="1.0", removed_in="2.0")
        all1 = reg.get_all()
        all1["injected"] = DeprecationInfo(  # type: ignore[assignment]
            name="injected", since="0", removed_in="0",
        )
        all2 = reg.get_all()
        assert "injected" not in all2

    def test_register_with_alternative(self):
        reg = DeprecationRegistry.get_instance()
        info = reg.register(
            "old_func", since="1.0", removed_in="2.0", alternative="new_func",
        )
        assert info.alternative == "new_func"

    def test_register_without_alternative(self):
        reg = DeprecationRegistry.get_instance()
        info = reg.register("old_func", since="1.0", removed_in="2.0")
        assert info.alternative is None

    def test_report_empty(self):
        reg = DeprecationRegistry.get_instance()
        report = reg.report()
        assert "0 items" in report
        assert "No deprecated APIs registered." in report

    def test_report_with_entries(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("old_func", since="1.0", removed_in="2.0",
                      alternative="new_func")
        reg.register("old_class", since="1.1", removed_in="3.0")
        report = reg.report()
        assert "2 items" in report
        assert "old_func" in report
        assert "old_class" in report
        assert "alternative=new_func" in report

    def test_report_sorted(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("z_func", since="1.0", removed_in="2.0")
        reg.register("a_func", since="1.0", removed_in="2.0")
        report = reg.report()
        a_pos = report.index("a_func")
        z_pos = report.index("z_func")
        assert a_pos < z_pos

    def test_report_dict_empty(self):
        reg = DeprecationRegistry.get_instance()
        result = reg.report_dict()
        assert result == []

    def test_report_dict_with_entries(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("func_a", since="1.0", removed_in="2.0",
                      alternative="func_b")
        result = reg.report_dict()
        assert len(result) == 1
        assert result[0]["name"] == "func_a"
        assert result[0]["alternative"] == "func_b"

    def test_report_dict_sorted(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("z_func", since="1.0", removed_in="2.0")
        reg.register("a_func", since="1.0", removed_in="2.0")
        result = reg.report_dict()
        assert result[0]["name"] == "a_func"
        assert result[1]["name"] == "z_func"

    def test_clear(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("old_func", since="1.0", removed_in="2.0")
        assert len(reg.get_all()) == 1
        reg.clear()
        assert len(reg.get_all()) == 0

    def test_reset_instance_creates_new(self):
        r1 = DeprecationRegistry.get_instance()
        r1.register("old_func", since="1.0", removed_in="2.0")
        DeprecationRegistry._reset_instance()
        r2 = DeprecationRegistry.get_instance()
        assert r1 is not r2
        assert len(r2.get_all()) == 0


# ======================================================================
# deprecated デコレータ（関数/メソッド用）
# ======================================================================

class TestDeprecatedDecorator:
    """deprecated デコレータのテスト。"""

    def test_function_still_works(self):
        @deprecated(since="1.0", removed_in="2.0")
        def old_func(x: int) -> int:
            return x * 2

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert old_func(5) == 10

    def test_warning_issued(self):
        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_warning_message_content(self):
        @deprecated(since="1.5", removed_in="2.0", alternative="new_func")
        def old_func() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            msg = str(w[0].message)
            assert "old_func" in msg
            assert "1.5" in msg
            assert "2.0" in msg
            assert "new_func" in msg

    def test_auto_registered_in_registry(self):
        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        reg = DeprecationRegistry.get_instance()
        all_entries = reg.get_all()
        # qualname includes the test function scope
        found = any("old_func" in name for name in all_entries)
        assert found

    def test_return_value_preserved(self):
        @deprecated(since="1.0", removed_in="2.0")
        def compute(a: int, b: int) -> int:
            return a + b

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert compute(3, 4) == 7

    def test_args_and_kwargs_preserved(self):
        @deprecated(since="1.0", removed_in="2.0")
        def func(a: int, b: int, *, c: str = "default") -> str:
            return f"{a}-{b}-{c}"

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = func(1, 2, c="custom")
            assert result == "1-2-custom"

    def test_method_on_class(self):
        class MyClass:
            @deprecated(since="1.0", removed_in="2.0")
            def old_method(self, x: int) -> int:
                return x + 1

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            obj = MyClass()
            result = obj.old_method(10)
            assert result == 11
            assert len(w) == 1

    def test_multiple_decorated_functions(self):
        @deprecated(since="1.0", removed_in="2.0")
        def func_a() -> str:
            return "a"

        @deprecated(since="1.1", removed_in="3.0")
        def func_b() -> str:
            return "b"

        reg = DeprecationRegistry.get_instance()
        assert len(reg.get_all()) == 2

    def test_decorator_without_alternative(self):
        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            msg = str(w[0].message)
            assert "instead" not in msg

    def test_warning_each_call(self):
        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            old_func()
            old_func()
            assert len(w) == 3

    def test_no_args_function(self):
        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> str:
            return "hello"

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert old_func() == "hello"

    def test_varargs_function(self):
        @deprecated(since="1.0", removed_in="2.0")
        def old_func(*args: Any, **kwargs: Any) -> tuple:
            return args, kwargs

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = old_func(1, 2, key="val")
            assert result == ((1, 2), {"key": "val"})


# ======================================================================
# deprecated_class デコレータ
# ======================================================================

class TestDeprecatedClassDecorator:
    """deprecated_class デコレータのテスト。"""

    def test_class_still_instantiable(self):
        @deprecated_class(since="1.0", removed_in="2.0")
        class OldClass:
            def __init__(self, value: int) -> None:
                self.value = value

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            obj = OldClass(42)
            assert obj.value == 42

    def test_warning_on_instantiation(self):
        @deprecated_class(since="1.0", removed_in="2.0")
        class OldClass:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            OldClass()
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_auto_registered_in_registry(self):
        @deprecated_class(since="1.0", removed_in="2.0", alternative="NewClass")
        class OldClass:
            pass

        reg = DeprecationRegistry.get_instance()
        all_entries = reg.get_all()
        found = any("OldClass" in name for name in all_entries)
        assert found

    def test_init_args_preserved(self):
        @deprecated_class(since="1.0", removed_in="2.0")
        class OldClass:
            def __init__(self, a: int, b: str, *, c: float = 1.0) -> None:
                self.a = a
                self.b = b
                self.c = c

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            obj = OldClass(1, "hello", c=3.14)
            assert obj.a == 1
            assert obj.b == "hello"
            assert obj.c == 3.14

    def test_class_methods_still_work(self):
        @deprecated_class(since="1.0", removed_in="2.0")
        class OldClass:
            def __init__(self, value: int) -> None:
                self.value = value

            def compute(self) -> int:
                return self.value * 2

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            obj = OldClass(5)
            assert obj.compute() == 10

    def test_class_without_init(self):
        @deprecated_class(since="1.0", removed_in="2.0")
        class SimpleClass:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            obj = SimpleClass()
            assert obj is not None
            assert len(w) == 1

    def test_warning_message_content(self):
        @deprecated_class(since="1.5", removed_in="2.0", alternative="NewClass")
        class OldClass:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            OldClass()
            msg = str(w[0].message)
            assert "OldClass" in msg
            assert "1.5" in msg
            assert "2.0" in msg
            assert "NewClass" in msg

    def test_multiple_instantiations_warn(self):
        @deprecated_class(since="1.0", removed_in="2.0")
        class OldClass:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            OldClass()
            OldClass()
            assert len(w) == 2

    def test_class_name_preserved(self):
        @deprecated_class(since="1.0", removed_in="2.0")
        class OldClass:
            pass

        assert OldClass.__name__ == "OldClass"


# ======================================================================
# 警告レベル制御
# ======================================================================

class TestDeprecationLevels:
    """RUMI_DEPRECATION_LEVEL 環境変数によるレベル制御テスト。"""

    def test_warn_level_issues_warning(self, monkeypatch):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "warn")

        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            assert len(w) == 1

    def test_error_level_raises_exception(self, monkeypatch):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "error")

        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with pytest.raises(DeprecationWarning, match="old_func"):
            old_func()

    def test_silent_level_no_warning(self, monkeypatch):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "silent")

        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            assert len(w) == 0

    def test_log_level_logs_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "log")

        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with caplog.at_level(logging.WARNING, logger="rumi.deprecation"):
            old_func()
            assert len(caplog.records) == 1
            assert "old_func" in caplog.records[0].message

    def test_default_is_warn(self, monkeypatch):
        monkeypatch.delenv("RUMI_DEPRECATION_LEVEL", raising=False)

        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            assert len(w) == 1

    def test_level_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "SILENT")

        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            assert len(w) == 0

    def test_unknown_level_defaults_to_warn(self, monkeypatch):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "unknown_value")

        @deprecated(since="1.0", removed_in="2.0")
        def old_func() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            old_func()
            assert len(w) == 1

    def test_error_level_with_class(self, monkeypatch):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "error")

        @deprecated_class(since="1.0", removed_in="2.0")
        class OldClass:
            pass

        with pytest.raises(DeprecationWarning, match="OldClass"):
            OldClass()

    def test_silent_level_with_class(self, monkeypatch):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "silent")

        @deprecated_class(since="1.0", removed_in="2.0")
        class OldClass:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            OldClass()
            assert len(w) == 0

    def test_log_level_with_class(self, monkeypatch, caplog):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "log")

        @deprecated_class(since="1.0", removed_in="2.0")
        class OldClass:
            pass

        with caplog.at_level(logging.WARNING, logger="rumi.deprecation"):
            OldClass()
            assert len(caplog.records) == 1
            assert "OldClass" in caplog.records[0].message


# ======================================================================
# async 関数対応
# ======================================================================

class TestAsyncDeprecated:
    """async 関数に対する deprecated デコレータのテスト。"""

    def test_async_function_still_works(self):
        @deprecated(since="1.0", removed_in="2.0")
        async def old_coro(x: int) -> int:
            return x * 3

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = asyncio.run(old_coro(5))
            assert result == 15

    def test_async_warning_issued(self):
        @deprecated(since="1.0", removed_in="2.0")
        async def old_coro() -> None:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            asyncio.run(old_coro())
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_async_auto_registered(self):
        @deprecated(since="1.0", removed_in="2.0", alternative="new_coro")
        async def old_coro() -> None:
            pass

        reg = DeprecationRegistry.get_instance()
        all_entries = reg.get_all()
        found = any("old_coro" in name for name in all_entries)
        assert found

    def test_async_return_value_preserved(self):
        @deprecated(since="1.0", removed_in="2.0")
        async def old_coro(a: str, b: str) -> str:
            return a + b

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = asyncio.run(old_coro("hello", " world"))
            assert result == "hello world"

    def test_async_error_level(self, monkeypatch):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "error")

        @deprecated(since="1.0", removed_in="2.0")
        async def old_coro() -> None:
            pass

        with pytest.raises(DeprecationWarning):
            asyncio.run(old_coro())


# ======================================================================
# functools.wraps による属性保持
# ======================================================================

class TestFuncToolsWraps:
    """functools.wraps による __name__, __doc__ 保持のテスト。"""

    def test_name_preserved(self):
        @deprecated(since="1.0", removed_in="2.0")
        def my_func() -> None:
            pass

        assert my_func.__name__ == "my_func"

    def test_doc_preserved(self):
        @deprecated(since="1.0", removed_in="2.0")
        def my_func() -> None:
            """This is the docstring."""
            pass

        assert my_func.__doc__ == "This is the docstring."

    def test_qualname_preserved(self):
        @deprecated(since="1.0", removed_in="2.0")
        def my_func() -> None:
            pass

        assert "my_func" in my_func.__qualname__

    def test_async_name_preserved(self):
        @deprecated(since="1.0", removed_in="2.0")
        async def my_async_func() -> None:
            pass

        assert my_async_func.__name__ == "my_async_func"

    def test_async_doc_preserved(self):
        @deprecated(since="1.0", removed_in="2.0")
        async def my_async_func() -> None:
            """Async docstring."""
            pass

        assert my_async_func.__doc__ == "Async docstring."

    def test_wrapped_attribute(self):
        @deprecated(since="1.0", removed_in="2.0")
        def my_func() -> None:
            pass

        assert hasattr(my_func, "__wrapped__")


# ======================================================================
# スレッドセーフ
# ======================================================================

class TestThreadSafety:
    """スレッドセーフのテスト。"""

    def test_concurrent_register(self):
        reg = DeprecationRegistry.get_instance()
        errors: List[Exception] = []

        def register_batch(prefix: str, count: int) -> None:
            try:
                for i in range(count):
                    reg.register(
                        f"{prefix}_{i}", since="1.0", removed_in="2.0",
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_batch, args=(f"thread_{t}", 50))
            for t in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        all_entries = reg.get_all()
        # 10 threads * 50 items = 500
        assert len(all_entries) == 500

    def test_concurrent_get_all(self):
        reg = DeprecationRegistry.get_instance()
        for i in range(100):
            reg.register(f"func_{i}", since="1.0", removed_in="2.0")

        results: List[Dict[str, DeprecationInfo]] = []
        errors: List[Exception] = []

        def read_all() -> None:
            try:
                for _ in range(50):
                    result = reg.get_all()
                    results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_all) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        for result in results:
            assert len(result) == 100

    def test_concurrent_deprecated_calls(self):
        @deprecated(since="1.0", removed_in="2.0")
        def old_func(x: int) -> int:
            return x * 2

        results: List[int] = []
        errors: List[Exception] = []

        def call_func(val: int) -> None:
            try:
                with warnings.catch_warnings(record=True):
                    warnings.simplefilter("always")
                    result = old_func(val)
                    results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=call_func, args=(i,))
            for i in range(100)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 100
        assert sorted(results) == [i * 2 for i in range(100)]


# ======================================================================
# エッジケース
# ======================================================================

class TestEdgeCases:
    """エッジケースのテスト。"""

    def test_get_deprecation_level_default(self, monkeypatch):
        monkeypatch.delenv("RUMI_DEPRECATION_LEVEL", raising=False)
        assert _get_deprecation_level() == "warn"

    def test_get_deprecation_level_custom(self, monkeypatch):
        monkeypatch.setenv("RUMI_DEPRECATION_LEVEL", "error")
        assert _get_deprecation_level() == "error"

    def test_emit_warning_directly(self):
        info = DeprecationInfo(name="test_func", since="1.0", removed_in="2.0")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _emit_deprecation_warning(info, stacklevel=1)
            assert len(w) == 1

    def test_registry_report_dict_structure(self):
        reg = DeprecationRegistry.get_instance()
        reg.register("func_a", since="1.0", removed_in="2.0",
                      alternative="func_b")
        reg.register("func_c", since="1.1", removed_in="3.0")
        result = reg.report_dict()
        assert isinstance(result, list)
        assert len(result) == 2
        for entry in result:
            assert "name" in entry
            assert "since" in entry
            assert "removed_in" in entry

    def test_decorated_staticmethod(self):
        class MyClass:
            @staticmethod
            @deprecated(since="1.0", removed_in="2.0")
            def old_static(x: int) -> int:
                return x + 10

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = MyClass.old_static(5)
            assert result == 15
            assert len(w) == 1

    def test_decorated_function_exception_propagates(self):
        @deprecated(since="1.0", removed_in="2.0")
        def bad_func() -> None:
            raise ValueError("original error")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            with pytest.raises(ValueError, match="original error"):
                bad_func()

    def test_deprecated_class_inheritance(self):
        @deprecated_class(since="1.0", removed_in="2.0")
        class Base:
            def __init__(self, x: int) -> None:
                self.x = x

        class Child(Base):
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            child = Child(42)
            assert child.x == 42
            assert len(w) == 1

    def test_report_contains_header(self):
        reg = DeprecationRegistry.get_instance()
        report = reg.report()
        assert "Deprecated API Report" in report
        assert "=" * 40 in report
