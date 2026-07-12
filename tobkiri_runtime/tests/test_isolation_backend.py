"""
test_isolation_backend.py - IsolationBackend ABC / IsolationResult テスト

テスト対象:
    - IsolationResult dataclass のデフォルト値
    - IsolationResult に全フィールドを指定した場合の値
    - IsolationBackend を直接インスタンス化できないこと (ABC 検証)
    - IsolationBackend を継承した DummyBackend で全メソッド実装後にインスタンス化できること
    - DummyBackend.execute() が IsolationResult を返すこと
    - DummyBackend.is_available() / get_name() が期待値を返すこと
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# テスト対象モジュールへのパスを通す
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core_runtime.isolation_backend import IsolationBackend, IsolationResult


# ============================================================
# テスト用ダミー実装
# ============================================================

class DummyBackend(IsolationBackend):
    """全抽象メソッドを実装したダミーバックエンド"""

    def execute(
        self,
        pack_id: str,
        script_path: Path,
        input_data: Any,
        context: Dict[str, Any],
        timeout: int = 60,
    ) -> IsolationResult:
        return IsolationResult(
            success=True,
            output={"pack_id": pack_id, "input": input_data},
            execution_time_ms=42.0,
        )

    def is_available(self) -> bool:
        return True

    def get_name(self) -> str:
        return "dummy"


class PartialBackend(IsolationBackend):
    """execute のみ実装し、is_available / get_name を欠いたバックエンド"""

    def execute(
        self,
        pack_id: str,
        script_path: Path,
        input_data: Any,
        context: Dict[str, Any],
        timeout: int = 60,
    ) -> IsolationResult:
        return IsolationResult(success=False)


# ============================================================
# IsolationResult テスト
# ============================================================

class TestIsolationResult:
    """IsolationResult dataclass のテスト"""

    def test_default_values(self):
        """必須フィールド (success) のみ指定した場合、他はデフォルト値"""
        result = IsolationResult(success=True)
        assert result.success is True
        assert result.output is None
        assert result.error is None
        assert result.error_type is None
        assert result.execution_time_ms == 0.0
        assert result.warnings == []

    def test_default_values_failure(self):
        """success=False の場合もデフォルト値が正しいこと"""
        result = IsolationResult(success=False)
        assert result.success is False
        assert result.output is None
        assert result.error is None
        assert result.error_type is None
        assert result.execution_time_ms == 0.0
        assert result.warnings == []

    def test_all_fields_specified(self):
        """全フィールドを指定した場合に正しく設定されること"""
        warnings_list = ["warn1", "warn2"]
        result = IsolationResult(
            success=False,
            output={"key": "value"},
            error="Something went wrong",
            error_type="timeout",
            execution_time_ms=123.456,
            warnings=warnings_list,
        )
        assert result.success is False
        assert result.output == {"key": "value"}
        assert result.error == "Something went wrong"
        assert result.error_type == "timeout"
        assert result.execution_time_ms == 123.456
        assert result.warnings == ["warn1", "warn2"]

    def test_warnings_default_factory_independence(self):
        """warnings のデフォルト値がインスタンス間で共有されないこと"""
        r1 = IsolationResult(success=True)
        r2 = IsolationResult(success=True)
        r1.warnings.append("only_r1")
        assert r1.warnings == ["only_r1"]
        assert r2.warnings == []


# ============================================================
# IsolationBackend ABC テスト
# ============================================================

class TestIsolationBackendABC:
    """IsolationBackend 抽象基底クラスのテスト"""

    def test_cannot_instantiate_directly(self):
        """IsolationBackend を直接インスタンス化すると TypeError"""
        with pytest.raises(TypeError):
            IsolationBackend()

    def test_cannot_instantiate_partial_implementation(self):
        """一部のメソッドしか実装していないサブクラスもインスタンス化不可"""
        with pytest.raises(TypeError):
            PartialBackend()

    def test_dummy_backend_instantiation(self):
        """全メソッドを実装した DummyBackend はインスタンス化できる"""
        backend = DummyBackend()
        assert isinstance(backend, IsolationBackend)
        assert isinstance(backend, DummyBackend)

    def test_dummy_backend_get_name(self):
        """DummyBackend.get_name() が 'dummy' を返すこと"""
        backend = DummyBackend()
        assert backend.get_name() == "dummy"

    def test_dummy_backend_is_available(self):
        """DummyBackend.is_available() が True を返すこと"""
        backend = DummyBackend()
        assert backend.is_available() is True

    def test_dummy_backend_execute_returns_isolation_result(self):
        """DummyBackend.execute() が IsolationResult を返すこと"""
        backend = DummyBackend()
        result = backend.execute(
            pack_id="test-pack",
            script_path=Path("/tmp/test.py"),
            input_data={"hello": "world"},
            context={"flow_id": "f1", "step_id": "s1"},
            timeout=30,
        )
        assert isinstance(result, IsolationResult)
        assert result.success is True
        assert result.output == {"pack_id": "test-pack", "input": {"hello": "world"}}
        assert result.execution_time_ms == 42.0
        assert result.error is None
        assert result.warnings == []

    def test_dummy_backend_execute_default_timeout(self):
        """DummyBackend.execute() を timeout 省略で呼べること"""
        backend = DummyBackend()
        result = backend.execute(
            pack_id="test-pack",
            script_path=Path("/tmp/test.py"),
            input_data=None,
            context={},
        )
        assert isinstance(result, IsolationResult)
        assert result.success is True

    def test_isolation_backend_is_abstract(self):
        """IsolationBackend が ABC のサブクラスであること"""
        from abc import ABC
        assert issubclass(IsolationBackend, ABC)
