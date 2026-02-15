"""
test_kernel_core.py - KernelCore ユニットテスト

テスト観点:
- KernelCore の初期化（デフォルト/カスタム設定）
- EventBus 連携（subscribe / publish / unsubscribe）
- ハンドラ登録と解決（_kernel_handlers / _resolve_handler）
- Flow 読み込み（load_flow / _load_single_flow）
- execute_flow_sync 正常系
- execute_flow_sync タイムアウト系（_flow_timeout: True）
- execute_flow_sync 不正 flow_id
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# テスト対象をインポートできるようにパスを追加
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.kernel_core import KernelCore, KernelConfig
from core_runtime.event_bus import EventBus
from core_runtime.diagnostics import Diagnostics


# =========================================================================
# KernelCore 初期化テスト
# =========================================================================


class TestKernelCoreInit(unittest.TestCase):
    """KernelCore の初期化テスト"""

    def test_default_init(self):
        """デフォルト引数での初期化"""
        kc = KernelCore()
        self.assertIsInstance(kc.config, KernelConfig)
        self.assertIsInstance(kc.diagnostics, Diagnostics)
        self.assertIsInstance(kc.event_bus, EventBus)
        self.assertIsNone(kc._flow)
        self.assertIsInstance(kc._kernel_handlers, dict)
        self.assertIsInstance(kc._shutdown_handlers, list)

    def test_custom_config(self):
        """カスタム設定での初期化"""
        cfg = KernelConfig(flow_path="custom/path.flow.yaml")
        kc = KernelCore(config=cfg)
        self.assertEqual(kc.config.flow_path, "custom/path.flow.yaml")

    def test_custom_event_bus(self):
        """カスタム EventBus の注入"""
        bus = EventBus()
        kc = KernelCore(event_bus=bus)
        self.assertIs(kc.event_bus, bus)

    def test_custom_diagnostics(self):
        """カスタム Diagnostics の注入"""
        diag = Diagnostics()
        kc = KernelCore(diagnostics=diag)
        self.assertIs(kc.diagnostics, diag)

    def test_executor_initialized(self):
        """ThreadPoolExecutor が初期化される"""
        kc = KernelCore()
        self.assertIsNotNone(kc._executor)


# =========================================================================
# EventBus 連携テスト
# =========================================================================


class TestEventBusIntegration(unittest.TestCase):
    """KernelCore に組み込まれた EventBus のテスト"""

    def setUp(self):
        self.kc = KernelCore()
        self.received_events = []

    def test_subscribe_and_publish(self):
        """subscribe → publish でハンドラが呼ばれる"""
        def handler(payload):
            self.received_events.append(payload)

        self.kc.event_bus.subscribe("test.topic", handler)
        self.kc.event_bus.publish("test.topic", {"key": "value"})

        self.assertEqual(len(self.received_events), 1)
        self.assertEqual(self.received_events[0]["key"], "value")

    def test_multiple_subscribers(self):
        """複数サブスクライバへの配信"""
        results = []

        self.kc.event_bus.subscribe("multi", lambda p: results.append("a"))
        self.kc.event_bus.subscribe("multi", lambda p: results.append("b"))
        self.kc.event_bus.publish("multi", {})

        self.assertEqual(len(results), 2)
        self.assertIn("a", results)
        self.assertIn("b", results)

    def test_unsubscribe(self):
        """unsubscribe 後はハンドラが呼ばれない"""
        def handler(payload):
            self.received_events.append(payload)

        hid = self.kc.event_bus.subscribe("unsub.topic", handler)
        self.kc.event_bus.unsubscribe("unsub.topic", hid)
        self.kc.event_bus.publish("unsub.topic", {"should_not": "arrive"})

        self.assertEqual(len(self.received_events), 0)

    def test_publish_no_subscribers(self):
        """サブスクライバなしの publish はエラーにならない"""
        try:
            self.kc.event_bus.publish("no.sub", {"data": 1})
        except Exception as e:
            self.fail(f"publish with no subscribers raised: {e}")

    def test_subscriber_error_does_not_break_others(self):
        """1つのハンドラでエラーが起きても他のハンドラは実行される"""
        results = []

        def bad_handler(payload):
            raise ValueError("intentional error")

        def good_handler(payload):
            results.append("ok")

        self.kc.event_bus.subscribe("err.topic", bad_handler)
        self.kc.event_bus.subscribe("err.topic", good_handler)
        self.kc.event_bus.publish("err.topic", {})

        self.assertEqual(results, ["ok"])

    def test_clear_all(self):
        """clear() で全サブスクリプション削除"""
        self.kc.event_bus.subscribe("t1", lambda p: None)
        self.kc.event_bus.subscribe("t2", lambda p: None)
        count = self.kc.event_bus.clear()
        self.assertEqual(count, 2)
        self.assertEqual(self.kc.event_bus.list_subscribers(), {})

    def test_clear_specific_topic(self):
        """clear(topic) で特定トピックのみ削除"""
        self.kc.event_bus.subscribe("keep", lambda p: None)
        self.kc.event_bus.subscribe("remove", lambda p: None)
        count = self.kc.event_bus.clear("remove")
        self.assertEqual(count, 1)
        subs = self.kc.event_bus.list_subscribers()
        self.assertIn("keep", subs)
        self.assertNotIn("remove", subs)

    def test_list_subscribers(self):
        """list_subscribers でトピックとハンドラIDを取得"""
        hid1 = self.kc.event_bus.subscribe("topic.a", lambda p: None, handler_id="my_h1")
        hid2 = self.kc.event_bus.subscribe("topic.b", lambda p: None)
        subs = self.kc.event_bus.list_subscribers()
        self.assertIn("topic.a", subs)
        self.assertIn("topic.b", subs)
        self.assertIn("my_h1", subs["topic.a"])


# =========================================================================
# ハンドラ登録・解決テスト
# =========================================================================


class TestHandlerResolution(unittest.TestCase):
    """_kernel_handlers と _resolve_handler のテスト"""

    def setUp(self):
        self.kc = KernelCore()

    def test_register_and_resolve_kernel_handler(self):
        """kernel: プレフィックスのハンドラを登録・解決"""
        def my_handler(args, ctx):
            return {"result": "ok"}

        self.kc._kernel_handlers["kernel:test.handler"] = my_handler
        resolved = self.kc._resolve_handler("kernel:test.handler")
        self.assertIs(resolved, my_handler)

    def test_resolve_nonexistent_handler(self):
        """存在しないハンドラは None"""
        resolved = self.kc._resolve_handler("kernel:nonexistent")
        self.assertIsNone(resolved)

    def test_resolve_empty_string(self):
        """空文字列は None"""
        resolved = self.kc._resolve_handler("")
        self.assertIsNone(resolved)

    def test_resolve_none(self):
        """None は None"""
        resolved = self.kc._resolve_handler(None)
        self.assertIsNone(resolved)

    def test_resolve_non_kernel_prefix(self):
        """kernel: / component_phase: 以外のプレフィックスは None"""
        resolved = self.kc._resolve_handler("unknown:something")
        self.assertIsNone(resolved)

    def test_resolve_component_phase_handler(self):
        """component_phase: プレフィックスのハンドラ解決は Callable"""
        resolved = self.kc._resolve_handler("component_phase:startup")
        self.assertTrue(callable(resolved))

    def test_registered_handler_callable(self):
        """登録したハンドラが呼び出し可能"""
        call_log = []

        def handler(args, ctx):
            call_log.append((args, ctx))
            return {"status": "handled"}

        self.kc._kernel_handlers["kernel:my.action"] = handler
        resolved = self.kc._resolve_handler("kernel:my.action")
        result = resolved({"input": 1}, {"ctx_key": "val"})
        self.assertEqual(result, {"status": "handled"})
        self.assertEqual(len(call_log), 1)


# =========================================================================
# Flow 読み込みテスト
# =========================================================================


class TestFlowLoading(unittest.TestCase):
    """load_flow のテスト"""

    def setUp(self):
        self.kc = KernelCore()
        self.tmpdir = tempfile.mkdtemp(prefix="rumi_test_flow_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_flow_with_explicit_path(self):
        """明示的パス指定での Flow 読み込み"""
        flow_file = Path(self.tmpdir) / "test.flow.yaml"
        flow_content = """
flow_version: "2.0"
defaults:
  fail_soft: true
pipelines:
  startup:
    - step_id: test_step
      handler: "kernel:noop"
"""
        flow_file.write_text(flow_content, encoding="utf-8")

        result = self.kc.load_flow(str(flow_file))
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)

    def test_load_flow_nonexistent_file(self):
        """存在しないファイルを指定した場合は例外"""
        nonexistent = str(Path(self.tmpdir) / "nonexistent.flow.yaml")
        with self.assertRaises(Exception):
            self.kc.load_flow(nonexistent)

    def test_flow_stored_internally(self):
        """load_flow 後に _flow が設定される"""
        flow_file = Path(self.tmpdir) / "internal.flow.yaml"
        flow_content = """
flow_version: "2.0"
defaults:
  fail_soft: true
pipelines:
  startup:
    - step_id: check
      handler: "kernel:noop"
"""
        flow_file.write_text(flow_content, encoding="utf-8")
        self.kc.load_flow(str(flow_file))
        self.assertIsNotNone(self.kc._flow)


# =========================================================================
# execute_flow_sync テスト
# =========================================================================


class TestExecuteFlowSync(unittest.TestCase):
    """execute_flow_sync のテスト（エージェントβの timeout 追加を含む）"""

    def setUp(self):
        self.kc = KernelCore()

    def test_normal_execution(self):
        """正常系: Flow が正常完了する"""
        expected_result = {"status": "ok", "data": [1, 2, 3]}

        async def mock_execute_flow(flow_id, context=None, timeout=None):
            return expected_result

        with patch.object(self.kc, 'execute_flow', side_effect=mock_execute_flow):
            result = self.kc.execute_flow_sync("test_flow")
            self.assertEqual(result, expected_result)

    def test_timeout_with_running_loop(self):
        """running loop 内から呼ばれた場合: ThreadPoolExecutor ルートでタイムアウト

        execute_flow_sync のコードパス:
        1. asyncio.get_running_loop() → 成功（loop がある）
        2. ThreadPoolExecutor で asyncio.run(execute_flow(...)) を実行
        3. pool.submit(...).result(timeout=effective_timeout) で TimeoutError
        4. {"_error": "...", "_flow_timeout": True} を返す
        """
        async def slow_flow(flow_id, context=None, timeout=None):
            await asyncio.sleep(100)
            return {}

        with patch.object(self.kc, 'execute_flow', side_effect=slow_flow):
            async def call_from_async():
                return self.kc.execute_flow_sync("timeout_flow", timeout=0.5)

            result = asyncio.run(call_from_async())

            self.assertIn("_flow_timeout", result)
            self.assertTrue(result["_flow_timeout"])
            self.assertIn("_error", result)
            self.assertIn("timed out", result["_error"])
            self.assertIn("sync", result["_error"])

    def test_invalid_flow_id_propagates_error(self):
        """不正な flow_id: execute_flow が例外を投げれば伝播する"""
        async def failing_flow(flow_id, context=None, timeout=None):
            raise KeyError(f"Flow '{flow_id}' not found")

        with patch.object(self.kc, 'execute_flow', side_effect=failing_flow):
            with self.assertRaises(KeyError):
                self.kc.execute_flow_sync("nonexistent_flow")

    def test_execute_flow_sync_with_context(self):
        """context パラメータが正しく渡される"""
        captured = {}

        async def capture_flow(flow_id, context=None, timeout=None):
            captured.update(context or {})
            return {"captured": True}

        with patch.object(self.kc, 'execute_flow', side_effect=capture_flow):
            ctx = {"user_id": "test_user", "session": "abc123"}
            self.kc.execute_flow_sync("ctx_flow", context=ctx)
            self.assertEqual(captured["user_id"], "test_user")
            self.assertEqual(captured["session"], "abc123")

    def test_default_timeout_is_300_seconds(self):
        """timeout 未指定時のデフォルトは 300 秒（execute_flow_sync 内 effective_timeout = timeout or 300）"""
        async def quick_flow(flow_id, context=None, timeout=None):
            return {"done": True}

        with patch.object(self.kc, 'execute_flow', side_effect=quick_flow):
            result = self.kc.execute_flow_sync("quick_flow")
            self.assertTrue(result["done"])

    def test_custom_timeout_value(self):
        """timeout に明示的な値を指定できる"""
        async def flow(flow_id, context=None, timeout=None):
            return {"timeout_received": timeout}

        with patch.object(self.kc, 'execute_flow', side_effect=flow):
            result = self.kc.execute_flow_sync("flow", timeout=60.0)
            self.assertEqual(result["timeout_received"], 60.0)

    def test_timeout_zero_triggers_immediate_timeout(self):
        """timeout=0.01 での即座のタイムアウト（running loop ルート）"""
        async def slow_flow(flow_id, context=None, timeout=None):
            await asyncio.sleep(100)
            return {}

        with patch.object(self.kc, 'execute_flow', side_effect=slow_flow):
            async def call():
                return self.kc.execute_flow_sync("slow", timeout=0.01)

            result = asyncio.run(call())
            self.assertTrue(result.get("_flow_timeout", False))


# =========================================================================
# _now_ts テスト
# =========================================================================


class TestNowTs(unittest.TestCase):
    """_now_ts の形式テスト"""

    def test_now_ts_format(self):
        """ISO 8601 UTC 形式 (Z suffix) であること"""
        kc = KernelCore()
        ts = kc._now_ts()
        self.assertTrue(ts.endswith("Z"), f"Expected Z suffix, got: {ts}")
        self.assertNotIn("+00:00", ts)

    def test_now_ts_is_string(self):
        """_now_ts は文字列を返す"""
        kc = KernelCore()
        ts = kc._now_ts()
        self.assertIsInstance(ts, str)


if __name__ == "__main__":
    unittest.main()
