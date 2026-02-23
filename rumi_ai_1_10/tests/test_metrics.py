"""
test_metrics.py - metrics ユニットテスト

テスト観点:
- MetricsCollector: カウンター/ゲージ/ヒストグラム/タイマー
- labels 付きメトリクス
- snapshot の構造
- reset
- スレッドセーフ動作
- get_metrics_collector: キャッシュ/リセット
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.metrics import (
    MetricsCollector,
    get_metrics_collector,
    reset_metrics_collector,
)


# =========================================================================
# MetricsCollector カウンターテスト
# =========================================================================


class TestCounter(unittest.TestCase):
    """カウンターのテスト"""

    def setUp(self):
        self.collector = MetricsCollector()

    def test_increment_basic(self):
        """基本的なカウンターインクリメント"""
        self.collector.increment("requests")
        snap = self.collector.snapshot()
        entries = snap["counters"]["requests"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["value"], 1.0)
        self.assertEqual(entries[0]["labels"], {})

    def test_increment_multiple(self):
        """複数回インクリメント"""
        self.collector.increment("requests")
        self.collector.increment("requests")
        self.collector.increment("requests")
        snap = self.collector.snapshot()
        self.assertEqual(snap["counters"]["requests"][0]["value"], 3.0)

    def test_increment_custom_value(self):
        """カスタム増加量"""
        self.collector.increment("bytes", value=1024)
        snap = self.collector.snapshot()
        self.assertEqual(snap["counters"]["bytes"][0]["value"], 1024.0)

    def test_increment_with_labels(self):
        """ラベル付きカウンター"""
        self.collector.increment("requests", labels={"method": "GET"})
        self.collector.increment("requests", labels={"method": "POST"})
        self.collector.increment("requests", labels={"method": "GET"})
        snap = self.collector.snapshot()
        entries = snap["counters"]["requests"]
        self.assertEqual(len(entries), 2)
        for entry in entries:
            if entry["labels"] == {"method": "GET"}:
                self.assertEqual(entry["value"], 2.0)
            elif entry["labels"] == {"method": "POST"}:
                self.assertEqual(entry["value"], 1.0)

    def test_increment_negative_raises(self):
        """負の値で ValueError"""
        with self.assertRaises(ValueError):
            self.collector.increment("bad", value=-1)


# =========================================================================
# MetricsCollector ゲージテスト
# =========================================================================


class TestGauge(unittest.TestCase):
    """ゲージのテスト"""

    def setUp(self):
        self.collector = MetricsCollector()

    def test_set_gauge_basic(self):
        """基本的なゲージ設定"""
        self.collector.set_gauge("connections", 42)
        snap = self.collector.snapshot()
        entries = snap["gauges"]["connections"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["value"], 42)

    def test_set_gauge_overwrite(self):
        """ゲージ値の上書き"""
        self.collector.set_gauge("connections", 10)
        self.collector.set_gauge("connections", 20)
        snap = self.collector.snapshot()
        self.assertEqual(snap["gauges"]["connections"][0]["value"], 20)

    def test_set_gauge_with_labels(self):
        """ラベル付きゲージ"""
        self.collector.set_gauge("temp", 36.5, labels={"sensor": "cpu"})
        self.collector.set_gauge("temp", 42.0, labels={"sensor": "gpu"})
        snap = self.collector.snapshot()
        entries = snap["gauges"]["temp"]
        self.assertEqual(len(entries), 2)


# =========================================================================
# MetricsCollector ヒストグラムテスト
# =========================================================================


class TestHistogram(unittest.TestCase):
    """ヒストグラムのテスト"""

    def setUp(self):
        self.collector = MetricsCollector()

    def test_observe_basic(self):
        """基本的な観測"""
        self.collector.observe("latency", 0.1)
        self.collector.observe("latency", 0.2)
        self.collector.observe("latency", 0.3)
        snap = self.collector.snapshot()
        hist = snap["histograms"]["latency"][0]
        self.assertEqual(hist["count"], 3)
        self.assertAlmostEqual(hist["sum"], 0.6, places=5)
        self.assertAlmostEqual(hist["min"], 0.1, places=5)
        self.assertAlmostEqual(hist["max"], 0.3, places=5)
        self.assertAlmostEqual(hist["avg"], 0.2, places=5)

    def test_observe_with_labels(self):
        """ラベル付きヒストグラム"""
        self.collector.observe("latency", 0.1, labels={"path": "/api"})
        self.collector.observe("latency", 0.5, labels={"path": "/web"})
        snap = self.collector.snapshot()
        entries = snap["histograms"]["latency"]
        self.assertEqual(len(entries), 2)

    def test_observe_single_value(self):
        """単一の観測値"""
        self.collector.observe("latency", 0.5)
        snap = self.collector.snapshot()
        hist = snap["histograms"]["latency"][0]
        self.assertEqual(hist["count"], 1)
        self.assertEqual(hist["min"], 0.5)
        self.assertEqual(hist["max"], 0.5)
        self.assertEqual(hist["avg"], 0.5)


# =========================================================================
# MetricsCollector タイマーテスト
# =========================================================================


class TestTimer(unittest.TestCase):
    """タイマーのテスト"""

    def setUp(self):
        self.collector = MetricsCollector()

    def test_timer_records_duration(self):
        """タイマーが処理時間を記録する"""
        with self.collector.timer("process_time"):
            time.sleep(0.05)
        snap = self.collector.snapshot()
        hist = snap["histograms"]["process_time"][0]
        self.assertEqual(hist["count"], 1)
        self.assertGreater(hist["sum"], 0.04)

    def test_timer_with_labels(self):
        """ラベル付きタイマー"""
        with self.collector.timer("duration", labels={"op": "read"}):
            time.sleep(0.01)
        snap = self.collector.snapshot()
        entries = snap["histograms"]["duration"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["labels"], {"op": "read"})

    def test_timer_records_on_exception(self):
        """例外が発生してもタイマーは記録する"""
        try:
            with self.collector.timer("error_time"):
                time.sleep(0.01)
                raise ValueError("test")
        except ValueError:
            pass
        snap = self.collector.snapshot()
        self.assertEqual(snap["histograms"]["error_time"][0]["count"], 1)


# =========================================================================
# MetricsCollector snapshot/reset テスト
# =========================================================================


class TestSnapshotAndReset(unittest.TestCase):
    """snapshot と reset のテスト"""

    def setUp(self):
        self.collector = MetricsCollector()

    def test_snapshot_empty(self):
        """空のスナップショット"""
        snap = self.collector.snapshot()
        self.assertEqual(snap["counters"], {})
        self.assertEqual(snap["gauges"], {})
        self.assertEqual(snap["histograms"], {})

    def test_snapshot_all_types(self):
        """全タイプのメトリクスがスナップショットに含まれる"""
        self.collector.increment("c1")
        self.collector.set_gauge("g1", 1)
        self.collector.observe("h1", 1.0)
        snap = self.collector.snapshot()
        self.assertIn("c1", snap["counters"])
        self.assertIn("g1", snap["gauges"])
        self.assertIn("h1", snap["histograms"])

    def test_reset_clears_all(self):
        """reset で全メトリクスがクリアされる"""
        self.collector.increment("c1")
        self.collector.set_gauge("g1", 1)
        self.collector.observe("h1", 1.0)
        self.collector.reset()
        snap = self.collector.snapshot()
        self.assertEqual(snap["counters"], {})
        self.assertEqual(snap["gauges"], {})
        self.assertEqual(snap["histograms"], {})


# =========================================================================
# スレッドセーフテスト
# =========================================================================


class TestThreadSafety(unittest.TestCase):
    """スレッドセーフ動作のテスト"""

    def test_concurrent_increments(self):
        """複数スレッドからの同時インクリメント"""
        collector = MetricsCollector()
        barrier = threading.Barrier(8)
        iterations = 100

        def increment_worker():
            barrier.wait(timeout=5)
            for _ in range(iterations):
                collector.increment("concurrent_counter")

        threads = [
            threading.Thread(target=increment_worker)
            for _ in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        snap = collector.snapshot()
        expected = 8 * iterations
        self.assertEqual(
            snap["counters"]["concurrent_counter"][0]["value"],
            expected,
        )


# =========================================================================
# get_metrics_collector テスト
# =========================================================================


class TestGetMetricsCollector(unittest.TestCase):
    """get_metrics_collector のテスト"""

    def setUp(self):
        reset_metrics_collector()

    def tearDown(self):
        reset_metrics_collector()

    def test_returns_metrics_collector(self):
        """MetricsCollector インスタンスを返す"""
        collector = get_metrics_collector()
        self.assertIsInstance(collector, MetricsCollector)

    def test_singleton(self):
        """同じインスタンスを返す"""
        c1 = get_metrics_collector()
        c2 = get_metrics_collector()
        self.assertIs(c1, c2)

    def test_reset(self):
        """reset 後は新しいインスタンスを返す"""
        c1 = get_metrics_collector()
        reset_metrics_collector()
        c2 = get_metrics_collector()
        self.assertIsNot(c1, c2)

    def test_thread_safe_singleton(self):
        """複数スレッドから同じインスタンスが返る"""
        results = {}
        barrier = threading.Barrier(4)

        def get_collector(idx):
            barrier.wait(timeout=5)
            results[idx] = get_metrics_collector()

        threads = [
            threading.Thread(target=get_collector, args=(i,))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        instances = list(results.values())
        for inst in instances[1:]:
            self.assertIs(inst, instances[0])


if __name__ == "__main__":
    unittest.main()
