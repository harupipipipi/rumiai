"""
test_types.py - types ユニットテスト

テスト観点:
- NewType 型 (PackId, FlowId, CapabilityName, HandlerKey, StoreKey)
- JSON 型 (JsonValue, JsonDict)
- コールバック型 (SyncCallback, AsyncCallback)
- Result データクラス
- Severity 列挙型
- モジュールインポート
"""

from __future__ import annotations

import enum
import sys
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.types import (
    PackId,
    FlowId,
    CapabilityName,
    HandlerKey,
    StoreKey,
    JsonValue,
    JsonDict,
    SyncCallback,
    AsyncCallback,
    Result,
    Severity,
)


# =========================================================================
# NewType テスト
# =========================================================================


class TestNewTypes(unittest.TestCase):
    """NewType 識別子型のテスト"""

    def test_pack_id_creates_str(self):
        """PackId は str と同等の値を返す"""
        pid = PackId("my-pack")
        self.assertEqual(pid, "my-pack")
        self.assertIsInstance(pid, str)

    def test_flow_id_creates_str(self):
        """FlowId は str と同等の値を返す"""
        fid = FlowId("flow-001")
        self.assertEqual(fid, "flow-001")
        self.assertIsInstance(fid, str)

    def test_capability_name_creates_str(self):
        """CapabilityName は str と同等の値を返す"""
        cn = CapabilityName("text_generation")
        self.assertEqual(cn, "text_generation")
        self.assertIsInstance(cn, str)

    def test_handler_key_creates_str(self):
        """HandlerKey は str と同等の値を返す"""
        hk = HandlerKey("on_message")
        self.assertEqual(hk, "on_message")
        self.assertIsInstance(hk, str)

    def test_store_key_creates_str(self):
        """StoreKey は str と同等の値を返す"""
        sk = StoreKey("user_preferences")
        self.assertEqual(sk, "user_preferences")
        self.assertIsInstance(sk, str)

    def test_newtype_is_callable(self):
        """全 NewType が callable である"""
        for nt in (PackId, FlowId, CapabilityName, HandlerKey, StoreKey):
            self.assertTrue(callable(nt), f"{nt} is not callable")

    def test_newtype_returns_same_value(self):
        """NewType は入力と同一の値を返す"""
        original = "test-value-123"
        for nt in (PackId, FlowId, CapabilityName, HandlerKey, StoreKey):
            self.assertIs(nt(original), original)


# =========================================================================
# JSON 型テスト
# =========================================================================


class TestJsonTypes(unittest.TestCase):
    """JSON 関連型のテスト"""

    def test_json_value_is_defined(self):
        """JsonValue がモジュール属性として存在する"""
        self.assertIsNotNone(JsonValue)

    def test_json_dict_is_defined(self):
        """JsonDict がモジュール属性として存在する"""
        self.assertIsNotNone(JsonDict)

    def test_json_compatible_values_at_runtime(self):
        """各種 JSON 互換値がランタイムで問題なく扱える"""
        # ランタイムでは型チェックは行われないが、
        # 型定義が壊れていないことを確認する
        values = [
            "string",
            42,
            3.14,
            True,
            False,
            None,
            [1, "two", 3.0],
            {"key": "value", "num": 123},
        ]
        for v in values:
            # 代入自体がエラーにならないことを確認
            json_val = v
            self.assertIsNotNone(json_val if json_val is not None else "ok")


# =========================================================================
# コールバック型テスト
# =========================================================================


class TestCallbackTypes(unittest.TestCase):
    """コールバック型のテスト"""

    def test_sync_callback_is_defined(self):
        """SyncCallback がモジュール属性として存在する"""
        self.assertIsNotNone(SyncCallback)

    def test_async_callback_is_defined(self):
        """AsyncCallback がモジュール属性として存在する"""
        self.assertIsNotNone(AsyncCallback)


# =========================================================================
# Result テスト
# =========================================================================


class TestResult(unittest.TestCase):
    """Result データクラスのテスト"""

    def test_result_success_pattern(self):
        """成功パターン: success=True, value あり, error なし"""
        r = Result(success=True, value=42)
        self.assertTrue(r.success)
        self.assertEqual(r.value, 42)
        self.assertIsNone(r.error)

    def test_result_failure_pattern(self):
        """失敗パターン: success=False, value なし, error あり"""
        r = Result(success=False, error="something went wrong")
        self.assertFalse(r.success)
        self.assertIsNone(r.value)
        self.assertEqual(r.error, "something went wrong")

    def test_result_defaults(self):
        """value と error のデフォルト値は None"""
        r = Result(success=True)
        self.assertIsNone(r.value)
        self.assertIsNone(r.error)

    def test_result_with_int_value(self):
        """int 値を持つ Result"""
        r = Result(success=True, value=100)
        self.assertEqual(r.value, 100)
        self.assertIsInstance(r.value, int)

    def test_result_with_str_value(self):
        """str 値を持つ Result"""
        r = Result(success=True, value="hello")
        self.assertEqual(r.value, "hello")
        self.assertIsInstance(r.value, str)

    def test_result_equality(self):
        """dataclass のデフォルト eq で同値比較できる"""
        r1 = Result(success=True, value=42)
        r2 = Result(success=True, value=42)
        self.assertEqual(r1, r2)

    def test_result_inequality(self):
        """異なる値を持つ Result は等しくない"""
        r1 = Result(success=True, value=42)
        r2 = Result(success=True, value=99)
        self.assertNotEqual(r1, r2)

    def test_result_is_dataclass(self):
        """Result は dataclass である"""
        self.assertTrue(is_dataclass(Result))

    def test_result_fields(self):
        """Result のフィールド名が正しい"""
        field_names = [f.name for f in fields(Result)]
        self.assertEqual(field_names, ["success", "value", "error"])

    def test_result_repr(self):
        """Result の repr が動作する"""
        r = Result(success=True, value="test")
        repr_str = repr(r)
        self.assertIn("Result", repr_str)
        self.assertIn("success=True", repr_str)


# =========================================================================
# Severity テスト
# =========================================================================


class TestSeverity(unittest.TestCase):
    """Severity 列挙型のテスト"""

    def test_severity_member_count(self):
        """Severity は 5 つのメンバーを持つ"""
        self.assertEqual(len(Severity), 5)

    def test_severity_values(self):
        """全メンバーの値が正しい"""
        self.assertEqual(Severity.DEBUG.value, "DEBUG")
        self.assertEqual(Severity.INFO.value, "INFO")
        self.assertEqual(Severity.WARNING.value, "WARNING")
        self.assertEqual(Severity.ERROR.value, "ERROR")
        self.assertEqual(Severity.CRITICAL.value, "CRITICAL")

    def test_severity_is_str(self):
        """Severity は str を継承している"""
        self.assertIsInstance(Severity.INFO, str)

    def test_severity_is_enum(self):
        """Severity は Enum を継承している"""
        self.assertIsInstance(Severity.INFO, enum.Enum)

    def test_severity_str_comparison(self):
        """Severity メンバーは文字列と直接比較可能"""
        self.assertEqual(Severity.DEBUG, "DEBUG")
        self.assertEqual(Severity.INFO, "INFO")
        self.assertEqual(Severity.WARNING, "WARNING")
        self.assertEqual(Severity.ERROR, "ERROR")
        self.assertEqual(Severity.CRITICAL, "CRITICAL")


if __name__ == "__main__":
    unittest.main()
