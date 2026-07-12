"""
test_logging_utils.py - logging_utils ユニットテスト

テスト観点:
- CorrelationContext: 設定/取得/ネスト/スレッド隔離/clear
- StructuredFormatter: JSON形式/テキスト形式/context_data/exc_info
- StructuredLogger: 各レベル出力/context_data/bind/互換性
- get_structured_logger: キャッシュ/リセット
- configure_logging: level/fmt/output設定/エラー
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import threading
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.logging_utils import (
    CorrelationContext,
    StructuredFormatter,
    StructuredLogger,
    get_structured_logger,
    get_correlation_id,
    set_correlation_id,
    clear_correlation_id,
    configure_logging,
    is_configured,
    reset_configuration,
    reset_logger_cache,
)


# =========================================================================
# CorrelationContext テスト
# =========================================================================


class TestCorrelationContext(unittest.TestCase):
    """CorrelationContext のテスト"""

    def setUp(self):
        clear_correlation_id()

    def tearDown(self):
        clear_correlation_id()

    def test_no_context_returns_none(self):
        """コンテキスト未設定時は None を返す"""
        self.assertIsNone(get_correlation_id())

    def test_context_manager_sets_id(self):
        """コンテキストマネージャで correlation_id が設定される"""
        with CorrelationContext(correlation_id="test-123"):
            self.assertEqual(get_correlation_id(), "test-123")

    def test_context_manager_restores_on_exit(self):
        """コンテキストマネージャ終了後に元の状態に戻る"""
        with CorrelationContext(correlation_id="test-456"):
            self.assertEqual(get_correlation_id(), "test-456")
        self.assertIsNone(get_correlation_id())

    def test_nested_context(self):
        """ネストされたコンテキストが正しく動作する"""
        with CorrelationContext(correlation_id="outer"):
            self.assertEqual(get_correlation_id(), "outer")
            with CorrelationContext(correlation_id="inner"):
                self.assertEqual(get_correlation_id(), "inner")
            self.assertEqual(get_correlation_id(), "outer")
        self.assertIsNone(get_correlation_id())

    def test_auto_generated_uuid(self):
        """correlation_id 未指定時は UUID が自動生成される"""
        with CorrelationContext() as ctx:
            self.assertIsNotNone(ctx.correlation_id)
            self.assertEqual(get_correlation_id(), ctx.correlation_id)
            # UUID 形式の長さ確認 (8-4-4-4-12 = 36文字)
            self.assertEqual(len(ctx.correlation_id), 36)

    def test_correlation_id_property(self):
        """correlation_id プロパティが正しい値を返す"""
        ctx = CorrelationContext(correlation_id="prop-test")
        self.assertEqual(ctx.correlation_id, "prop-test")

    def test_set_correlation_id(self):
        """set_correlation_id で直接設定できる"""
        set_correlation_id("direct-set")
        self.assertEqual(get_correlation_id(), "direct-set")

    def test_clear_correlation_id(self):
        """clear_correlation_id でクリアされる"""
        set_correlation_id("to-clear")
        self.assertEqual(get_correlation_id(), "to-clear")
        clear_correlation_id()
        self.assertIsNone(get_correlation_id())

    def test_thread_isolation(self):
        """異なるスレッド間で correlation_id が隔離される"""
        results = {}
        barrier = threading.Barrier(2)

        def thread_func(thread_name, corr_id):
            with CorrelationContext(correlation_id=corr_id):
                barrier.wait(timeout=5)
                results[thread_name] = get_correlation_id()

        t1 = threading.Thread(target=thread_func, args=("t1", "id-t1"))
        t2 = threading.Thread(target=thread_func, args=("t2", "id-t2"))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        self.assertEqual(results["t1"], "id-t1")
        self.assertEqual(results["t2"], "id-t2")

    def test_deeply_nested_context(self):
        """3段以上のネストが正しく動作する"""
        with CorrelationContext(correlation_id="level-1"):
            self.assertEqual(get_correlation_id(), "level-1")
            with CorrelationContext(correlation_id="level-2"):
                self.assertEqual(get_correlation_id(), "level-2")
                with CorrelationContext(correlation_id="level-3"):
                    self.assertEqual(get_correlation_id(), "level-3")
                self.assertEqual(get_correlation_id(), "level-2")
            self.assertEqual(get_correlation_id(), "level-1")
        self.assertIsNone(get_correlation_id())


# =========================================================================
# StructuredFormatter テスト
# =========================================================================


class TestStructuredFormatter(unittest.TestCase):
    """StructuredFormatter のテスト"""

    def _make_record(self, msg="test message", level=logging.INFO,
                     name="rumi.test", context_data=None):
        """テスト用の LogRecord を作成する"""
        record = logging.LogRecord(
            name=name,
            level=level,
            pathname="test.py",
            lineno=42,
            msg=msg,
            args=(),
            exc_info=None,
        )
        if context_data is not None:
            record.context_data = context_data
        return record

    def test_json_format_basic(self):
        """JSON形式の基本フォーマット"""
        formatter = StructuredFormatter(fmt_type="json")
        record = self._make_record()
        output = formatter.format(record)
        parsed = json.loads(output)

        self.assertIn("timestamp", parsed)
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["module"], "rumi.test")
        self.assertEqual(parsed["message"], "test message")
        self.assertIn("correlation_id", parsed)

    def test_json_format_with_context_data(self):
        """JSON形式で context_data が含まれる"""
        formatter = StructuredFormatter(fmt_type="json")
        record = self._make_record(
            context_data={"pack_id": "my-pack", "flow_id": "startup"}
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        self.assertEqual(parsed["pack_id"], "my-pack")
        self.assertEqual(parsed["flow_id"], "startup")

    def test_json_format_with_correlation_id(self):
        """JSON形式で correlation_id が含まれる"""
        clear_correlation_id()
        formatter = StructuredFormatter(fmt_type="json")

        with CorrelationContext(correlation_id="corr-json"):
            record = self._make_record()
            output = formatter.format(record)
            parsed = json.loads(output)
            self.assertEqual(parsed["correlation_id"], "corr-json")

        clear_correlation_id()

    def test_json_timestamp_format(self):
        """JSON形式のタイムスタンプが ISO8601 UTC (Z suffix) である"""
        formatter = StructuredFormatter(fmt_type="json")
        record = self._make_record()
        output = formatter.format(record)
        parsed = json.loads(output)

        self.assertTrue(parsed["timestamp"].endswith("Z"))
        self.assertNotIn("+00:00", parsed["timestamp"])

    def test_text_format_basic(self):
        """テキスト形式の基本フォーマット"""
        clear_correlation_id()
        formatter = StructuredFormatter(fmt_type="text")
        record = self._make_record()
        output = formatter.format(record)

        self.assertIn("[INFO]", output)
        self.assertIn("rumi.test", output)
        self.assertIn("test message", output)
        clear_correlation_id()

    def test_text_format_with_correlation_id(self):
        """テキスト形式で correlation_id が含まれる"""
        clear_correlation_id()
        formatter = StructuredFormatter(fmt_type="text")

        with CorrelationContext(correlation_id="corr-text"):
            record = self._make_record()
            output = formatter.format(record)
            self.assertIn("correlation_id=corr-text", output)

        clear_correlation_id()

    def test_text_format_with_context_data(self):
        """テキスト形式で context_data が含まれる"""
        clear_correlation_id()
        formatter = StructuredFormatter(fmt_type="text")
        record = self._make_record(
            context_data={"pack_id": "my-pack"}
        )
        output = formatter.format(record)
        self.assertIn("pack_id=my-pack", output)
        clear_correlation_id()

    def test_env_variable_selects_text(self):
        """環境変数 RUMI_LOG_FORMAT=text でテキスト形式になる"""
        with patch.dict(os.environ, {"RUMI_LOG_FORMAT": "text"}):
            formatter = StructuredFormatter()
            self.assertEqual(formatter.fmt_type, "text")

    def test_env_variable_default_json(self):
        """環境変数未設定時は JSON 形式"""
        env = os.environ.copy()
        env.pop("RUMI_LOG_FORMAT", None)
        with patch.dict(os.environ, env, clear=True):
            formatter = StructuredFormatter()
            self.assertEqual(formatter.fmt_type, "json")

    def test_json_format_with_exception(self):
        """JSON形式で例外情報が含まれる"""
        formatter = StructuredFormatter(fmt_type="json")
        try:
            raise ValueError("test error")
        except ValueError:
            record = self._make_record()
            record.exc_info = sys.exc_info()

        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertIn("exception", parsed)
        self.assertIn("ValueError", parsed["exception"])
        self.assertIn("test error", parsed["exception"])

    def test_json_context_data_does_not_overwrite_core_fields(self):
        """context_data のキーがコアフィールドを上書きしない"""
        formatter = StructuredFormatter(fmt_type="json")
        record = self._make_record(
            context_data={"timestamp": "should-not-overwrite", "level": "FAKE"}
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        # コアフィールドは上書きされない
        self.assertNotEqual(parsed["timestamp"], "should-not-overwrite")
        self.assertNotEqual(parsed["level"], "FAKE")


# =========================================================================
# StructuredLogger テスト
# =========================================================================


class TestStructuredLogger(unittest.TestCase):
    """StructuredLogger のテスト"""

    def setUp(self):
        clear_correlation_id()
        self._handler = logging.StreamHandler(StringIO())
        self._handler.setFormatter(StructuredFormatter(fmt_type="json"))
        self._handler.setLevel(logging.DEBUG)

    def tearDown(self):
        clear_correlation_id()

    def _get_output(self) -> str:
        return self._handler.stream.getvalue()

    def _get_parsed_lines(self):
        output = self._get_output()
        lines = [line for line in output.strip().split("\n") if line.strip()]
        return [json.loads(line) for line in lines]

    def _make_logger(self, name="rumi.test.structured"):
        logger = StructuredLogger(name)
        # 既存ハンドラをクリアしてテスト用ハンドラを追加
        logger.logger.handlers.clear()
        logger.logger.addHandler(self._handler)
        logger.logger.setLevel(logging.DEBUG)
        logger.logger.propagate = False
        return logger

    def test_info_log(self):
        """info() でINFOレベルのログが出力される"""
        logger = self._make_logger()
        logger.info("hello world")

        entries = self._get_parsed_lines()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["level"], "INFO")
        self.assertEqual(entries[0]["message"], "hello world")

    def test_debug_log(self):
        """debug() でDEBUGレベルのログが出力される"""
        logger = self._make_logger()
        logger.debug("debug msg")

        entries = self._get_parsed_lines()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["level"], "DEBUG")

    def test_warning_log(self):
        """warning() でWARNINGレベルのログが出力される"""
        logger = self._make_logger()
        logger.warning("warn msg")

        entries = self._get_parsed_lines()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["level"], "WARNING")

    def test_error_log(self):
        """error() でERRORレベルのログが出力される"""
        logger = self._make_logger()
        logger.error("error msg")

        entries = self._get_parsed_lines()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["level"], "ERROR")

    def test_critical_log(self):
        """critical() でCRITICALレベルのログが出力される"""
        logger = self._make_logger()
        logger.critical("critical msg")

        entries = self._get_parsed_lines()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["level"], "CRITICAL")

    def test_context_data_in_log(self):
        """ログに context_data が含まれる"""
        logger = self._make_logger()
        logger.info("with context", pack_id="pk-1", flow_id="fl-1")

        entries = self._get_parsed_lines()
        self.assertEqual(entries[0]["pack_id"], "pk-1")
        self.assertEqual(entries[0]["flow_id"], "fl-1")

    def test_bind_creates_new_logger(self):
        """bind() が新しい StructuredLogger を返す"""
        logger = self._make_logger()
        bound = logger.bind(pack_id="bound-pack")
        self.assertIsNot(logger, bound)
        self.assertEqual(bound.name, logger.name)

    def test_bind_context_in_log(self):
        """bind() で設定したコンテキストがログに含まれる"""
        logger = self._make_logger()
        bound = logger.bind(pack_id="bound-pack")
        # bound logger も同じ内部 Logger を使う（同じハンドラ）
        bound.info("bound message")

        entries = self._get_parsed_lines()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["pack_id"], "bound-pack")

    def test_bind_chain(self):
        """bind() のチェーンが正しく動作する"""
        logger = self._make_logger()
        bound1 = logger.bind(pack_id="pk-1")
        bound2 = bound1.bind(flow_id="fl-2")
        bound2.info("chained")

        entries = self._get_parsed_lines()
        self.assertEqual(entries[0]["pack_id"], "pk-1")
        self.assertEqual(entries[0]["flow_id"], "fl-2")

    def test_bind_override(self):
        """bind() で同じキーを上書きできる"""
        logger = self._make_logger()
        bound1 = logger.bind(pack_id="original")
        bound2 = bound1.bind(pack_id="overridden")
        bound2.info("override test")

        entries = self._get_parsed_lines()
        self.assertEqual(entries[0]["pack_id"], "overridden")

    def test_call_context_overrides_bind(self):
        """呼び出し時のコンテキストが bind のコンテキストを上書きする"""
        logger = self._make_logger()
        bound = logger.bind(pack_id="from-bind")
        bound.info("override", pack_id="from-call")

        entries = self._get_parsed_lines()
        self.assertEqual(entries[0]["pack_id"], "from-call")

    def test_logger_property(self):
        """logger プロパティで内部の logging.Logger にアクセスできる"""
        logger = self._make_logger()
        self.assertIsInstance(logger.logger, logging.Logger)

    def test_name_property(self):
        """name プロパティが正しい値を返す"""
        logger = StructuredLogger("rumi.my.module")
        self.assertEqual(logger.name, "rumi.my.module")

    def test_is_enabled_for(self):
        """isEnabledFor が正しく動作する"""
        logger = self._make_logger()
        logger.setLevel(logging.WARNING)
        self.assertFalse(logger.isEnabledFor(logging.DEBUG))
        self.assertTrue(logger.isEnabledFor(logging.WARNING))
        self.assertTrue(logger.isEnabledFor(logging.ERROR))

    def test_set_level(self):
        """setLevel が正しく動作する"""
        logger = self._make_logger()
        logger.setLevel(logging.ERROR)
        self.assertEqual(logger.getEffectiveLevel(), logging.ERROR)

    def test_exception_log(self):
        """exception() で例外情報付きログが出力される"""
        logger = self._make_logger()
        try:
            raise RuntimeError("test exception")
        except RuntimeError:
            logger.exception("caught error")

        entries = self._get_parsed_lines()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["level"], "ERROR")
        self.assertIn("exception", entries[0])
        self.assertIn("RuntimeError", entries[0]["exception"])

    def test_correlation_id_in_log(self):
        """CorrelationContext 内のログに correlation_id が含まれる"""
        logger = self._make_logger()
        with CorrelationContext(correlation_id="corr-in-log"):
            logger.info("with correlation")

        entries = self._get_parsed_lines()
        self.assertEqual(entries[0]["correlation_id"], "corr-in-log")

    def test_level_filtering(self):
        """レベルフィルタリングが正しく動作する"""
        logger = self._make_logger()
        logger.setLevel(logging.WARNING)

        logger.debug("should not appear")
        logger.info("should not appear")
        logger.warning("should appear")

        entries = self._get_parsed_lines()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["message"], "should appear")


# =========================================================================
# get_structured_logger テスト
# =========================================================================


class TestGetStructuredLogger(unittest.TestCase):
    """get_structured_logger のテスト"""

    def setUp(self):
        reset_logger_cache()

    def tearDown(self):
        reset_logger_cache()

    def test_returns_structured_logger(self):
        """StructuredLogger インスタンスを返す"""
        logger = get_structured_logger("rumi.test.factory")
        self.assertIsInstance(logger, StructuredLogger)

    def test_same_name_returns_same_instance(self):
        """同じ name に対しては同じインスタンスを返す"""
        logger1 = get_structured_logger("rumi.test.cache")
        logger2 = get_structured_logger("rumi.test.cache")
        self.assertIs(logger1, logger2)

    def test_different_name_returns_different_instance(self):
        """異なる name に対しては異なるインスタンスを返す"""
        logger1 = get_structured_logger("rumi.test.a")
        logger2 = get_structured_logger("rumi.test.b")
        self.assertIsNot(logger1, logger2)

    def test_reset_cache(self):
        """reset_logger_cache でキャッシュがクリアされる"""
        logger1 = get_structured_logger("rumi.test.reset")
        reset_logger_cache()
        logger2 = get_structured_logger("rumi.test.reset")
        self.assertIsNot(logger1, logger2)

    def test_thread_safe_creation(self):
        """複数スレッドから同じ name で同じインスタンスが返る"""
        results = {}
        barrier = threading.Barrier(4)

        def get_logger(thread_id):
            barrier.wait(timeout=5)
            results[thread_id] = get_structured_logger("rumi.test.threadsafe")

        threads = [
            threading.Thread(target=get_logger, args=(i,))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # 全て同じインスタンス
        instances = list(results.values())
        for inst in instances[1:]:
            self.assertIs(inst, instances[0])


# =========================================================================
# configure_logging テスト
# =========================================================================


class TestConfigureLogging(unittest.TestCase):
    """configure_logging のテスト"""

    def setUp(self):
        reset_configuration()
        reset_logger_cache()

    def tearDown(self):
        reset_configuration()
        reset_logger_cache()

    def test_configure_sets_configured(self):
        """configure_logging 後に is_configured() が True になる"""
        self.assertFalse(is_configured())
        configure_logging(level="INFO", fmt="json", output="stderr")
        self.assertTrue(is_configured())

    def test_reset_configuration(self):
        """reset_configuration で is_configured() が False に戻る"""
        configure_logging(level="INFO", fmt="json", output="stderr")
        self.assertTrue(is_configured())
        reset_configuration()
        self.assertFalse(is_configured())

    def test_invalid_level_raises(self):
        """無効なログレベルで ValueError が発生する"""
        with self.assertRaises(ValueError):
            configure_logging(level="INVALID", fmt="json", output="stderr")

    def test_configure_json_format(self):
        """JSON形式での設定が正しく適用される"""
        configure_logging(level="DEBUG", fmt="json", output="stderr")
        rumi_logger = logging.getLogger("rumi")
        self.assertEqual(rumi_logger.level, logging.DEBUG)
        self.assertEqual(len(rumi_logger.handlers), 1)
        self.assertIsInstance(rumi_logger.handlers[0].formatter, StructuredFormatter)

    def test_configure_text_format(self):
        """テキスト形式での設定が正しく適用される"""
        configure_logging(level="INFO", fmt="text", output="stderr")
        rumi_logger = logging.getLogger("rumi")
        formatter = rumi_logger.handlers[0].formatter
        self.assertIsInstance(formatter, StructuredFormatter)
        self.assertEqual(formatter.fmt_type, "text")

    def test_configure_file_output(self):
        """ファイル出力での設定が正しく適用される"""
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name

        try:
            configure_logging(level="INFO", fmt="json", output=log_path)
            rumi_logger = logging.getLogger("rumi")
            self.assertEqual(len(rumi_logger.handlers), 1)
            self.assertIsInstance(rumi_logger.handlers[0], logging.FileHandler)
        finally:
            reset_configuration()
            try:
                os.unlink(log_path)
            except OSError:
                pass

    def test_configure_replaces_handlers(self):
        """再設定で既存ハンドラが置き換えられる"""
        configure_logging(level="INFO", fmt="json", output="stderr")
        configure_logging(level="DEBUG", fmt="text", output="stderr")

        rumi_logger = logging.getLogger("rumi")
        self.assertEqual(len(rumi_logger.handlers), 1)
        self.assertEqual(rumi_logger.level, logging.DEBUG)

    def test_configure_propagate_false(self):
        """設定後に rumi ロガーの propagate が False"""
        configure_logging(level="INFO", fmt="json", output="stderr")
        rumi_logger = logging.getLogger("rumi")
        self.assertFalse(rumi_logger.propagate)

    def test_child_logger_inherits_handler(self):
        """子ロガー（rumi.xxx）が rumi の設定を継承する"""
        configure_logging(level="DEBUG", fmt="json", output="stderr")

        child_logger = logging.getLogger("rumi.kernel.core")
        # 子ロガーのeffective levelが親から継承されるか確認
        self.assertEqual(child_logger.getEffectiveLevel(), logging.DEBUG)

    def test_all_valid_levels(self):
        """全ての有効なログレベルが設定できる"""
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            reset_configuration()
            configure_logging(level=level, fmt="json", output="stderr")
            rumi_logger = logging.getLogger("rumi")
            expected = getattr(logging, level)
            self.assertEqual(rumi_logger.level, expected, f"Level {level} failed")


# =========================================================================
# 統合テスト
# =========================================================================


class TestIntegration(unittest.TestCase):
    """統合テスト"""

    def setUp(self):
        clear_correlation_id()
        reset_configuration()
        reset_logger_cache()

    def tearDown(self):
        clear_correlation_id()
        reset_configuration()
        reset_logger_cache()
        # 統合テストで使ったロガーのハンドラをクリア
        for name in ("rumi", "rumi.integration.test", "rumi.integration.text"):
            lg = logging.getLogger(name)
            lg.handlers.clear()

    def test_full_flow_json(self):
        """完全なフロー: configure → get_logger → CorrelationContext → log → JSON出力"""
        # StringIO でキャプチャ
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter(fmt_type="json"))
        handler.setLevel(logging.DEBUG)

        rumi_logger = logging.getLogger("rumi")
        rumi_logger.handlers.clear()
        rumi_logger.addHandler(handler)
        rumi_logger.setLevel(logging.DEBUG)
        rumi_logger.propagate = False

        logger = get_structured_logger("rumi.integration.test")
        bound = logger.bind(pack_id="integration-pack")

        with CorrelationContext(correlation_id="int-corr-001"):
            bound.info("integration test", flow_id="test-flow", step_id="step-1")

        output = stream.getvalue().strip()
        parsed = json.loads(output)

        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["module"], "rumi.integration.test")
        self.assertEqual(parsed["message"], "integration test")
        self.assertEqual(parsed["correlation_id"], "int-corr-001")
        self.assertEqual(parsed["pack_id"], "integration-pack")
        self.assertEqual(parsed["flow_id"], "test-flow")
        self.assertEqual(parsed["step_id"], "step-1")
        self.assertTrue(parsed["timestamp"].endswith("Z"))

    def test_full_flow_text(self):
        """完全なフロー: テキスト形式での出力"""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter(fmt_type="text"))
        handler.setLevel(logging.DEBUG)

        rumi_logger = logging.getLogger("rumi")
        rumi_logger.handlers.clear()
        rumi_logger.addHandler(handler)
        rumi_logger.setLevel(logging.DEBUG)
        rumi_logger.propagate = False

        logger = get_structured_logger("rumi.integration.text")

        with CorrelationContext(correlation_id="text-corr"):
            logger.info("text mode test", pack_id="text-pack")

        output = stream.getvalue().strip()
        self.assertIn("[INFO]", output)
        self.assertIn("rumi.integration.text", output)
        self.assertIn("text mode test", output)
        self.assertIn("correlation_id=text-corr", output)
        self.assertIn("pack_id=text-pack", output)

    def test_existing_logger_compatibility(self):
        """既存の logging.getLogger() パターンとの互換性"""
        # 既存パターン: logging.getLogger("rumi.kernel.core")
        existing_logger = logging.getLogger("rumi.kernel.core")

        # StructuredLogger でも同じ名前で取得
        structured = get_structured_logger("rumi.kernel.core")

        # 内部の logging.Logger は同じインスタンス
        self.assertIs(structured.logger, existing_logger)


if __name__ == "__main__":
    unittest.main()
