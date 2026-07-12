"""
W20-D: _RateLimiter unit tests.

Tests the _RateLimiter class directly without starting the HTTP server.
The class source is extracted from pack_api_server.py and exec'd in an
isolated namespace so that core_runtime package imports are not needed.
"""
import collections
import os
import re
import threading
import time
from pathlib import Path as _Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# _RateLimiter クラスを pack_api_server.py のソースから抽出して exec でロード
# core_runtime パッケージの import を完全に回避する
# ---------------------------------------------------------------------------
_SRC_FILE = _Path(__file__).resolve().parent.parent / "core_runtime" / "pack_api_server.py"
_source = _SRC_FILE.read_text(encoding="utf-8")

# class _RateLimiter: から次のモジュールレベル定義直前までを抽出
_m = re.search(r"(class _RateLimiter\b.*?)(?=\n[^ \n#])", _source, re.DOTALL)
assert _m, "_RateLimiter class not found in pack_api_server.py"
_class_src = _m.group(1)

_ns: dict = {
    "threading": threading,
    "time": time,
    "collections": collections,
    "os": os,
    "__builtins__": __builtins__,
}
exec(_class_src, _ns)
_RateLimiter = _ns["_RateLimiter"]


# ---------------------------------------------------------------------------
# Helper: deterministic monotonic mock
# ---------------------------------------------------------------------------
class FakeClock:
    """time.monotonic の代替。手動で時間を進められる。"""
    def __init__(self, start: float = 1000.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRateLimiterBasic:

    def test_within_limit(self):
        """制限内のリクエストは全て許可される。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=5, window_seconds=60)
        with patch("time.monotonic", clock):
            for i in range(5):
                assert rl.is_allowed("10.0.0.1") is True, f"Request {i+1} should be allowed"

    def test_exceed_limit(self):
        """制限超過のリクエストは拒否される。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=3, window_seconds=60)
        with patch("time.monotonic", clock):
            for _ in range(3):
                assert rl.is_allowed("10.0.0.1") is True
            assert rl.is_allowed("10.0.0.1") is False
            assert rl.is_allowed("10.0.0.1") is False

    def test_window_expiry(self):
        """ウィンドウ時間経過後は再びリクエスト可能。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=2, window_seconds=10)
        with patch("time.monotonic", clock):
            assert rl.is_allowed("10.0.0.1") is True
            assert rl.is_allowed("10.0.0.1") is True
            assert rl.is_allowed("10.0.0.1") is False

            # ウィンドウ経過
            clock.advance(11)
            assert rl.is_allowed("10.0.0.1") is True

    def test_different_ips_independent(self):
        """異なる IP は独立してカウントされる。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=2, window_seconds=60)
        with patch("time.monotonic", clock):
            assert rl.is_allowed("10.0.0.1") is True
            assert rl.is_allowed("10.0.0.1") is True
            assert rl.is_allowed("10.0.0.1") is False
            # 別 IP は独立
            assert rl.is_allowed("10.0.0.2") is True
            assert rl.is_allowed("10.0.0.2") is True
            assert rl.is_allowed("10.0.0.2") is False


class TestRateLimiterEnv:

    def test_custom_rate_limit_env(self):
        """RUMI_API_RATE_LIMIT 環境変数でカスタム制限値が反映される。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=int(os.environ.get("RUMI_API_RATE_LIMIT", "2")),
                          window_seconds=60)
        with patch("time.monotonic", clock):
            assert rl.is_allowed("10.0.0.1") is True
            assert rl.is_allowed("10.0.0.1") is True
            assert rl.is_allowed("10.0.0.1") is False

    def test_custom_window_env(self):
        """RUMI_API_RATE_WINDOW 環境変数でカスタムウィンドウが反映される。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=1,
                          window_seconds=float(os.environ.get("RUMI_API_RATE_WINDOW", "5")))
        with patch("time.monotonic", clock):
            assert rl.is_allowed("10.0.0.1") is True
            assert rl.is_allowed("10.0.0.1") is False
            clock.advance(6)
            assert rl.is_allowed("10.0.0.1") is True


class TestRateLimiterCleanup:

    def test_old_timestamps_cleanup(self):
        """古いタイムスタンプがクリーンアップされる。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=3, window_seconds=10)
        with patch("time.monotonic", clock):
            assert rl.is_allowed("10.0.0.1") is True   # t=1000
            clock.advance(4)
            assert rl.is_allowed("10.0.0.1") is True   # t=1004
            clock.advance(4)
            assert rl.is_allowed("10.0.0.1") is True   # t=1008
            assert rl.is_allowed("10.0.0.1") is False   # 3/3 in window

            # t=1000 のエントリがウィンドウ外に
            clock.advance(3)  # t=1011 -> window cutoff=1001
            assert rl.is_allowed("10.0.0.1") is True

    def test_max_tracked_ips(self):
        """最大追跡 IP 数の制限が機能する。"""
        clock = FakeClock()
        max_ips = 5
        rl = _RateLimiter(max_requests=100, window_seconds=60, max_ips=max_ips)
        with patch("time.monotonic", clock):
            for i in range(max_ips):
                clock.advance(0.001)
                assert rl.is_allowed(f"10.0.0.{i}") is True

            clock.advance(0.001)
            assert rl.is_allowed("10.0.0.99") is True
            with rl._lock:
                assert len(rl._requests) <= max_ips

    def test_evict_frees_slot(self):
        """最古 IP 除去後に新 IP が追加可能。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=10, window_seconds=60, max_ips=2)
        with patch("time.monotonic", clock):
            assert rl.is_allowed("A") is True
            clock.advance(1)
            assert rl.is_allowed("B") is True
            clock.advance(1)
            assert rl.is_allowed("C") is True
            with rl._lock:
                assert len(rl._requests) <= 2


class TestRateLimiterThreadSafety:

    def test_thread_safety(self):
        """スレッドセーフ: 並列リクエストでデータ破壊が起きない。"""
        rl = _RateLimiter(max_requests=1000, window_seconds=60)
        errors = []
        barrier = threading.Barrier(10)

        def worker(ip: str):
            try:
                barrier.wait(timeout=5)
                for _ in range(100):
                    rl.is_allowed(ip)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(f"10.0.0.{i}",))
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errors in threads: {errors}"
        total = 0
        with rl._lock:
            for dq in rl._requests.values():
                total += len(dq)
        assert total == 1000  # 10 threads x 100 requests


class TestRateLimiterLocalhost:

    def test_localhost_rate_limited(self):
        """127.0.0.1 からのリクエストにもレート制限が適用される。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=2, window_seconds=60)
        with patch("time.monotonic", clock):
            assert rl.is_allowed("127.0.0.1") is True
            assert rl.is_allowed("127.0.0.1") is True
            assert rl.is_allowed("127.0.0.1") is False

    def test_exactly_at_limit(self):
        """ちょうど制限値のリクエストは許可され、次は拒否される。"""
        clock = FakeClock()
        rl = _RateLimiter(max_requests=5, window_seconds=60)
        with patch("time.monotonic", clock):
            for _ in range(5):
                assert rl.is_allowed("10.0.0.1") is True
            assert rl.is_allowed("10.0.0.1") is False
