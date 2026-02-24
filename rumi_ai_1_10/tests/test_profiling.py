"""
test_profiling.py - profiling ユニットテスト

テスト観点:
- Profiler: コンテキストマネージャ / sync デコレータ / async デコレータ
- 統計の正確性（count, total, avg, min, max, p50, p95, p99）
- メモリ制限（max_samples 超過時の挙動）
- スレッドセーフ動作
- report / report_dict
- clear / sections
- get_profiler / reset_profiler: シングルトン / リセット / スレッドセーフ
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import unittest
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core_runtime.profiling import (
    Profiler,
    get_profiler,
    reset_profiler,
)


# =========================================================================
# コンテキストマネージャテスト
# =========================================================================


class TestProfileContextManager(unittest.TestCase):
    """profile() コンテキストマネージャのテスト"""

    def setUp(self):
        self.profiler = Profiler()

    def test_basic(self):
        """基本的なコンテキストマネージャ計測"""
        with self.profiler.profile("section_a"):
            pass
        stats = self.profiler.get_stats("section_a")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["count"], 1)
        self.assertGreaterEqual(stats["total_time"], 0.0)

    def test_records_time(self):
        """時間が正しく記録される"""
        with self.profiler.profile("timed"):
            time.sleep(0.05)
        stats = self.profiler.get_stats("timed")
        self.assertGreater(stats["total_time"], 0.04)

    def test_exception_still_records(self):
        """例外が発生しても計測結果は記録される"""
        try:
            with self.profiler.profile("error_section"):
                time.sleep(0.01)
                raise ValueError("test error")
        except ValueError:
            pass
        stats = self.profiler.get_stats("error_section")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["count"], 1)
        self.assertGreater(stats["total_time"], 0.0)

    def test_nested(self):
        """ネストした計測"""
        with self.profiler.profile("outer"):
            time.sleep(0.01)
            with self.profiler.profile("inner"):
                time.sleep(0.01)
        outer = self.profiler.get_stats("outer")
        inner = self.profiler.get_stats("inner")
        self.assertIsNotNone(outer)
        self.assertIsNotNone(inner)
        self.assertGreater(outer["total_time"], inner["total_time"])

    def test_multiple_sections(self):
        """複数区間の計測"""
        with self.profiler.profile("section_x"):
            pass
        with self.profiler.profile("section_y"):
            pass
        with self.profiler.profile("section_z"):
            pass
        self.assertEqual(len(self.profiler.sections()), 3)

    def test_multiple_calls_same_section(self):
        """同一区間の複数回呼び出し"""
        for _ in range(5):
            with self.profiler.profile("repeated"):
                pass
        stats = self.profiler.get_stats("repeated")
        self.assertEqual(stats["count"], 5)


# =========================================================================
# sync デコレータテスト
# =========================================================================


class TestProfileFunc(unittest.TestCase):
    """profile_func デコレータのテスト"""

    def setUp(self):
        self.profiler = Profiler()

    def test_basic(self):
        """基本的な sync デコレータ計測"""

        @self.profiler.profile_func
        def my_func():
            time.sleep(0.01)

        my_func()
        stats = self.profiler.get_stats("TestProfileFunc.test_basic.<locals>.my_func")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["count"], 1)

    def test_preserves_return_value(self):
        """デコレータが戻り値を保持する"""

        @self.profiler.profile_func
        def add(a, b):
            return a + b

        result = add(3, 4)
        self.assertEqual(result, 7)

    def test_preserves_metadata(self):
        """functools.wraps によりメタデータが保持される"""

        @self.profiler.profile_func
        def documented_func():
            """This is a docstring."""
            pass

        self.assertEqual(documented_func.__name__, "documented_func")
        self.assertEqual(documented_func.__doc__, "This is a docstring.")

    def test_exception_still_records(self):
        """例外が発生しても計測結果は記録される"""

        @self.profiler.profile_func
        def failing_func():
            raise RuntimeError("fail")

        with self.assertRaises(RuntimeError):
            failing_func()

        sections = self.profiler.sections()
        self.assertEqual(len(sections), 1)
        stats = self.profiler.get_stats(sections[0])
        self.assertEqual(stats["count"], 1)

    def test_with_args_and_kwargs(self):
        """引数付き関数のデコレータ"""

        @self.profiler.profile_func
        def compute(x, y, factor=1):
            return (x + y) * factor

        result = compute(2, 3, factor=10)
        self.assertEqual(result, 50)
        sections = self.profiler.sections()
        self.assertEqual(len(sections), 1)


# =========================================================================
# async デコレータテスト
# =========================================================================


class TestProfileAsync(unittest.TestCase):
    """profile_async デコレータのテスト"""

    def setUp(self):
        self.profiler = Profiler()

    def test_basic(self):
        """基本的な async デコレータ計測"""

        @self.profiler.profile_async
        async def async_work():
            await asyncio.sleep(0.01)

        asyncio.run(async_work())
        sections = self.profiler.sections()
        self.assertEqual(len(sections), 1)
        stats = self.profiler.get_stats(sections[0])
        self.assertEqual(stats["count"], 1)
        self.assertGreater(stats["total_time"], 0.005)

    def test_preserves_return_value(self):
        """async デコレータが戻り値を保持する"""

        @self.profiler.profile_async
        async def async_add(a, b):
            return a + b

        result = asyncio.run(async_add(10, 20))
        self.assertEqual(result, 30)

    def test_preserves_metadata(self):
        """async functools.wraps によりメタデータが保持される"""

        @self.profiler.profile_async
        async def async_documented():
            """Async docstring."""
            pass

        self.assertEqual(async_documented.__name__, "async_documented")
        self.assertEqual(async_documented.__doc__, "Async docstring.")

    def test_exception_still_records(self):
        """async で例外が発生しても計測結果は記録される"""

        @self.profiler.profile_async
        async def async_fail():
            raise RuntimeError("async fail")

        with self.assertRaises(RuntimeError):
            asyncio.run(async_fail())

        sections = self.profiler.sections()
        self.assertEqual(len(sections), 1)
        stats = self.profiler.get_stats(sections[0])
        self.assertEqual(stats["count"], 1)


# =========================================================================
# 統計テスト
# =========================================================================


class TestStatistics(unittest.TestCase):
    """統計計算の正確性テスト"""

    def setUp(self):
        self.profiler = Profiler(max_samples=10000)

    def _record_values(self, name, values):
        """テスト用にサンプルを直接記録する。"""
        for v in values:
            self.profiler._record(name, v)

    def test_count(self):
        """呼出回数が正確"""
        self._record_values("cnt", [0.1, 0.2, 0.3])
        stats = self.profiler.get_stats("cnt")
        self.assertEqual(stats["count"], 3)

    def test_total_time(self):
        """合計時間が正確"""
        self._record_values("tot", [0.1, 0.2, 0.3])
        stats = self.profiler.get_stats("tot")
        self.assertAlmostEqual(stats["total_time"], 0.6, places=5)

    def test_avg_time(self):
        """平均時間が正確"""
        self._record_values("avg", [0.1, 0.2, 0.3])
        stats = self.profiler.get_stats("avg")
        self.assertAlmostEqual(stats["avg_time"], 0.2, places=5)

    def test_min_max(self):
        """最小/最大が正確"""
        self._record_values("mm", [0.5, 0.1, 0.9, 0.3])
        stats = self.profiler.get_stats("mm")
        self.assertAlmostEqual(stats["min_time"], 0.1, places=5)
        self.assertAlmostEqual(stats["max_time"], 0.9, places=5)

    def test_p50(self):
        """p50（中央値）が正確"""
        values = [float(i) for i in range(1, 101)]
        self._record_values("p50test", values)
        stats = self.profiler.get_stats("p50test")
        self.assertAlmostEqual(stats["p50"], 50.0, places=5)

    def test_p95(self):
        """p95 が正確"""
        values = [float(i) for i in range(1, 101)]
        self._record_values("p95test", values)
        stats = self.profiler.get_stats("p95test")
        self.assertAlmostEqual(stats["p95"], 95.0, places=5)

    def test_p99(self):
        """p99 が正確"""
        values = [float(i) for i in range(1, 101)]
        self._record_values("p99test", values)
        stats = self.profiler.get_stats("p99test")
        self.assertAlmostEqual(stats["p99"], 99.0, places=5)

    def test_single_sample_percentiles(self):
        """サンプル1件でもパーセンタイルが返る"""
        self._record_values("single", [0.42])
        stats = self.profiler.get_stats("single")
        self.assertAlmostEqual(stats["p50"], 0.42, places=5)
        self.assertAlmostEqual(stats["p95"], 0.42, places=5)
        self.assertAlmostEqual(stats["p99"], 0.42, places=5)

    def test_unknown_section_returns_none(self):
        """存在しない区間は None を返す"""
        result = self.profiler.get_stats("nonexistent")
        self.assertIsNone(result)


# =========================================================================
# レポートテスト
# =========================================================================


class TestReport(unittest.TestCase):
    """report / report_dict のテスト"""

    def setUp(self):
        self.profiler = Profiler()

    def test_report_dict_structure(self):
        """report_dict の構造が正しい"""
        self.profiler._record("sec_a", 0.1)
        self.profiler._record("sec_b", 0.2)
        data = self.profiler.report_dict()
        self.assertIn("sections", data)
        self.assertIn("sec_a", data["sections"])
        self.assertIn("sec_b", data["sections"])
        for name, stats in data["sections"].items():
            self.assertIn("count", stats)
            self.assertIn("total_time", stats)
            self.assertIn("avg_time", stats)
            self.assertIn("min_time", stats)
            self.assertIn("max_time", stats)
            self.assertIn("p50", stats)
            self.assertIn("p95", stats)
            self.assertIn("p99", stats)

    def test_report_dict_empty(self):
        """空の report_dict"""
        data = self.profiler.report_dict()
        self.assertEqual(data["sections"], {})

    def test_report_text_contains_sections(self):
        """テキストレポートに区間名が含まれる"""
        self.profiler._record("my_section", 0.123)
        text = self.profiler.report()
        self.assertIn("Performance Profile Report", text)
        self.assertIn("my_section", text)
        self.assertIn("Count:", text)
        self.assertIn("P99:", text)

    def test_report_text_empty(self):
        """空のテキストレポート"""
        text = self.profiler.report()
        self.assertIn("no data", text)

    def test_report_text_sorted(self):
        """テキストレポートの区間がソートされている"""
        self.profiler._record("zzz", 0.1)
        self.profiler._record("aaa", 0.2)
        text = self.profiler.report()
        pos_aaa = text.index("aaa")
        pos_zzz = text.index("zzz")
        self.assertLess(pos_aaa, pos_zzz)


# =========================================================================
# クリア・セクションテスト
# =========================================================================


class TestClearAndSections(unittest.TestCase):
    """clear / sections のテスト"""

    def setUp(self):
        self.profiler = Profiler()

    def test_clear(self):
        """clear で全データがクリアされる"""
        self.profiler._record("a", 0.1)
        self.profiler._record("b", 0.2)
        self.profiler.clear()
        self.assertEqual(self.profiler.sections(), [])
        self.assertIsNone(self.profiler.get_stats("a"))

    def test_sections_list(self):
        """sections() が登録済み区間名を返す"""
        self.profiler._record("alpha", 0.1)
        self.profiler._record("beta", 0.2)
        names = self.profiler.sections()
        self.assertIn("alpha", names)
        self.assertIn("beta", names)
        self.assertEqual(len(names), 2)

    def test_clear_then_reuse(self):
        """clear 後に再利用できる"""
        self.profiler._record("x", 0.1)
        self.profiler.clear()
        self.profiler._record("x", 0.5)
        stats = self.profiler.get_stats("x")
        self.assertEqual(stats["count"], 1)
        self.assertAlmostEqual(stats["total_time"], 0.5, places=5)


# =========================================================================
# メモリ制限テスト
# =========================================================================


class TestMaxSamples(unittest.TestCase):
    """max_samples メモリ制限のテスト"""

    def test_default_max_samples(self):
        """デフォルト max_samples は 1000"""
        profiler = Profiler()
        self.assertEqual(profiler.max_samples, 1000)

    def test_custom_max_samples(self):
        """カスタム max_samples"""
        profiler = Profiler(max_samples=50)
        self.assertEqual(profiler.max_samples, 50)

    def test_invalid_max_samples(self):
        """max_samples < 1 で ValueError"""
        with self.assertRaises(ValueError):
            Profiler(max_samples=0)
        with self.assertRaises(ValueError):
            Profiler(max_samples=-1)

    def test_overflow_count_accurate(self):
        """max_samples 超過時も count は正確"""
        profiler = Profiler(max_samples=10)
        for i in range(100):
            profiler._record("overflow", float(i))
        stats = profiler.get_stats("overflow")
        self.assertEqual(stats["count"], 100)

    def test_overflow_total_time_accurate(self):
        """max_samples 超過時も total_time は正確"""
        profiler = Profiler(max_samples=5)
        expected_total = 0.0
        for i in range(20):
            val = float(i) * 0.1
            expected_total += val
            profiler._record("ov_total", val)
        stats = profiler.get_stats("ov_total")
        self.assertAlmostEqual(stats["total_time"], expected_total, places=5)

    def test_overflow_min_max_accurate(self):
        """max_samples 超過時も min/max は正確"""
        profiler = Profiler(max_samples=5)
        profiler._record("ov_mm", 0.001)
        for i in range(20):
            profiler._record("ov_mm", 0.5)
        profiler._record("ov_mm", 9.999)
        for i in range(20):
            profiler._record("ov_mm", 0.5)
        stats = profiler.get_stats("ov_mm")
        self.assertAlmostEqual(stats["min_time"], 0.001, places=5)
        self.assertAlmostEqual(stats["max_time"], 9.999, places=5)

    def test_overflow_samples_limited(self):
        """max_samples 超過時にサンプル数が制限される"""
        profiler = Profiler(max_samples=10)
        for i in range(100):
            profiler._record("limited", float(i))
        with profiler._lock:
            samples = profiler._sections["limited"]["samples"]
            self.assertEqual(len(samples), 10)

    def test_overflow_percentiles_from_recent(self):
        """max_samples 超過時にパーセンタイルは最新サンプルから計算"""
        profiler = Profiler(max_samples=10)
        # 最初に小さい値を100個入れる（溢れる）
        for _ in range(100):
            profiler._record("recent_p", 0.001)
        # 次に大きい値を10個入れる（dequeに残る）
        for _ in range(10):
            profiler._record("recent_p", 1.0)
        stats = profiler.get_stats("recent_p")
        # p50 は deque 内の最新10件（全て1.0）から計算される
        self.assertAlmostEqual(stats["p50"], 1.0, places=5)


# =========================================================================
# スレッドセーフテスト
# =========================================================================


class TestThreadSafety(unittest.TestCase):
    """スレッドセーフ動作のテスト"""

    def test_concurrent_records(self):
        """複数スレッドからの同時記録"""
        profiler = Profiler()
        barrier = threading.Barrier(8)
        iterations = 100

        def worker():
            barrier.wait(timeout=5)
            for _ in range(iterations):
                profiler._record("concurrent", 0.001)

        threads = [
            threading.Thread(target=worker)
            for _ in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        stats = profiler.get_stats("concurrent")
        self.assertEqual(stats["count"], 8 * iterations)

    def test_concurrent_context_manager(self):
        """複数スレッドからのコンテキストマネージャ同時使用"""
        profiler = Profiler()
        barrier = threading.Barrier(4)
        iterations = 50

        def worker():
            barrier.wait(timeout=5)
            for _ in range(iterations):
                with profiler.profile("cm_concurrent"):
                    pass

        threads = [
            threading.Thread(target=worker)
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        stats = profiler.get_stats("cm_concurrent")
        self.assertEqual(stats["count"], 4 * iterations)

    def test_concurrent_different_sections(self):
        """複数スレッドが異なる区間を同時に記録"""
        profiler = Profiler()
        barrier = threading.Barrier(4)
        iterations = 50

        def worker(section_name):
            barrier.wait(timeout=5)
            for _ in range(iterations):
                profiler._record(section_name, 0.001)

        threads = [
            threading.Thread(target=worker, args=(f"section_{i}",))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for i in range(4):
            stats = profiler.get_stats(f"section_{i}")
            self.assertEqual(stats["count"], iterations)


# =========================================================================
# get_profiler / reset_profiler テスト
# =========================================================================


class TestGetProfiler(unittest.TestCase):
    """get_profiler / reset_profiler のテスト"""

    def setUp(self):
        reset_profiler()

    def tearDown(self):
        reset_profiler()

    def test_returns_profiler(self):
        """Profiler インスタンスを返す"""
        profiler = get_profiler()
        self.assertIsInstance(profiler, Profiler)

    def test_singleton(self):
        """同じインスタンスを返す"""
        p1 = get_profiler()
        p2 = get_profiler()
        self.assertIs(p1, p2)

    def test_reset(self):
        """reset 後は新しいインスタンスを返す"""
        p1 = get_profiler()
        reset_profiler()
        p2 = get_profiler()
        self.assertIsNot(p1, p2)

    def test_thread_safe_singleton(self):
        """複数スレッドから同じインスタンスが返る"""
        results = {}
        barrier = threading.Barrier(4)

        def get_prof(idx):
            barrier.wait(timeout=5)
            results[idx] = get_profiler()

        threads = [
            threading.Thread(target=get_prof, args=(i,))
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
