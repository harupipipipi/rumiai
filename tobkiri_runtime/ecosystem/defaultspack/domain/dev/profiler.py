"""Dev Profiler — パフォーマンス計測を管理する。

機能:
    - ブロック実行時間の記録
    - AI API コールのレイテンシ記録
    - メモリ使用量のスナップショット
    - プロファイル結果の取得

インメモリ保存。シングルトンパターン。スレッドセーフ。
"""

import os
import time
import threading
from collections import deque
from contextlib import contextmanager


class Profiler:
    """パフォーマンスプロファイラのシングルトン。"""

    _instance = None
    _lock = threading.Lock()
    MAX_ENTRIES = 500

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._data_lock = threading.Lock()
        self._enabled = True

        # ブロック実行時間: deque of {"block_name": str, "duration_ms": float, "timestamp": str, "success": bool}
        self._block_timings: deque = deque(maxlen=self.MAX_ENTRIES)

        # AI APIコールレイテンシ: deque of {"model": str, "duration_ms": float, "timestamp": str, "token_count": int}
        self._api_timings: deque = deque(maxlen=self.MAX_ENTRIES)

        # メモリスナップショット: deque of {"rss_mb": float, "vms_mb": float, "timestamp": str, "label": str}
        self._memory_snapshots: deque = deque(maxlen=self.MAX_ENTRIES)

    # ------------------------------------------------------------------
    # 有効/無効
    # ------------------------------------------------------------------

    def enable(self) -> None:
        """プロファイラを有効にする。"""
        self._enabled = True

    def disable(self) -> None:
        """プロファイラを無効にする。"""
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        """プロファイラが有効かどうか。"""
        return self._enabled

    # ------------------------------------------------------------------
    # ブロック実行時間
    # ------------------------------------------------------------------

    def record_block(
        self,
        block_name: str,
        duration_ms: float,
        success: bool = True,
        metadata: dict | None = None,
    ) -> dict:
        """ブロックの実行時間を記録する。

        Args:
            block_name:  ブロック名（例: "blocks.dev.inspect"）
            duration_ms: 実行時間（ミリ秒）
            success:     実行が成功したか
            metadata:    追加メタデータ

        Returns:
            記録されたエントリ dict
        """
        if not self._enabled:
            return {}
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        entry = {
            "block_name": block_name,
            "duration_ms": round(duration_ms, 3),
            "success": success,
            "metadata": dict(metadata or {}),
            "timestamp": now,
        }
        with self._data_lock:
            self._block_timings.append(entry)
        return entry

    @contextmanager
    def measure_block(self, block_name: str, metadata: dict | None = None):
        """ブロック実行時間をコンテキストマネージャで計測する。

        使用例:
            profiler = Profiler()
            with profiler.measure_block("blocks.dev.inspect"):
                result = run(input_data, context)
        """
        start = time.perf_counter()
        success = True
        try:
            yield
        except Exception:
            success = False
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.record_block(block_name, elapsed_ms, success=success, metadata=metadata)

    def get_block_timings(self, limit: int = 50, block_name: str | None = None) -> list[dict]:
        """ブロック実行時間の記録を新しい順で返す。

        Args:
            limit:      取得件数上限
            block_name: フィルタ用ブロック名（Noneで全件）

        Returns:
            [{"block_name": str, "duration_ms": float, "success": bool, "timestamp": str}, ...]
        """
        with self._data_lock:
            data = list(self._block_timings)
        if block_name is not None:
            data = [e for e in data if e["block_name"] == block_name]
        data.reverse()
        return data[:limit]

    def get_block_summary(self) -> list[dict]:
        """ブロック別の実行統計サマリーを返す。

        Returns:
            [{"block_name": str, "call_count": int, "avg_ms": float, "min_ms": float,
              "max_ms": float, "total_ms": float, "success_rate": float}, ...]
        """
        with self._data_lock:
            data = list(self._block_timings)

        # ブロック別に集計
        stats: dict[str, dict] = {}
        for entry in data:
            name = entry["block_name"]
            if name not in stats:
                stats[name] = {
                    "block_name": name,
                    "durations": [],
                    "success_count": 0,
                    "total_count": 0,
                }
            stats[name]["durations"].append(entry["duration_ms"])
            stats[name]["total_count"] += 1
            if entry["success"]:
                stats[name]["success_count"] += 1

        result = []
        for name, s in stats.items():
            durations = s["durations"]
            total_count = s["total_count"]
            result.append({
                "block_name": name,
                "call_count": total_count,
                "avg_ms": round(sum(durations) / len(durations), 3) if durations else 0.0,
                "min_ms": round(min(durations), 3) if durations else 0.0,
                "max_ms": round(max(durations), 3) if durations else 0.0,
                "total_ms": round(sum(durations), 3),
                "success_rate": round(s["success_count"] / total_count, 4) if total_count > 0 else 0.0,
            })
        result.sort(key=lambda x: x["total_ms"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # AI API コールレイテンシ
    # ------------------------------------------------------------------

    def record_api_call(
        self,
        model: str,
        duration_ms: float,
        token_count: int = 0,
        metadata: dict | None = None,
    ) -> dict:
        """AI APIコールのレイテンシを記録する。

        Args:
            model:       モデル名
            duration_ms: レイテンシ（ミリ秒）
            token_count: トークン数
            metadata:    追加メタデータ

        Returns:
            記録されたエントリ dict
        """
        if not self._enabled:
            return {}
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        entry = {
            "model": model,
            "duration_ms": round(duration_ms, 3),
            "token_count": token_count,
            "metadata": dict(metadata or {}),
            "timestamp": now,
        }
        with self._data_lock:
            self._api_timings.append(entry)
        return entry

    @contextmanager
    def measure_api_call(self, model: str, metadata: dict | None = None):
        """AI APIコールのレイテンシをコンテキストマネージャで計測する。

        yield に {"token_count": int} を渡すと記録される。

        使用例:
            profiler = Profiler()
            with profiler.measure_api_call("openai/gpt-4") as ctx:
                result = client.complete(...)
                ctx["token_count"] = result.get("usage", {}).get("total_tokens", 0)
        """
        start = time.perf_counter()
        ctx = {"token_count": 0}
        try:
            yield ctx
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.record_api_call(
                model=model,
                duration_ms=elapsed_ms,
                token_count=ctx.get("token_count", 0),
                metadata=metadata,
            )

    def get_api_timings(self, limit: int = 50, model: str | None = None) -> list[dict]:
        """AI APIコールのレイテンシ記録を新しい順で返す。

        Args:
            limit: 取得件数上限
            model: フィルタ用モデル名（Noneで全件）

        Returns:
            [{"model": str, "duration_ms": float, "token_count": int, "timestamp": str}, ...]
        """
        with self._data_lock:
            data = list(self._api_timings)
        if model is not None:
            data = [e for e in data if e["model"] == model]
        data.reverse()
        return data[:limit]

    def get_api_summary(self) -> list[dict]:
        """モデル別のAPIコール統計サマリーを返す。

        Returns:
            [{"model": str, "call_count": int, "avg_ms": float, "min_ms": float,
              "max_ms": float, "total_tokens": int}, ...]
        """
        with self._data_lock:
            data = list(self._api_timings)

        stats: dict[str, dict] = {}
        for entry in data:
            model = entry["model"]
            if model not in stats:
                stats[model] = {
                    "model": model,
                    "durations": [],
                    "total_tokens": 0,
                }
            stats[model]["durations"].append(entry["duration_ms"])
            stats[model]["total_tokens"] += entry.get("token_count", 0)

        result = []
        for model, s in stats.items():
            durations = s["durations"]
            result.append({
                "model": model,
                "call_count": len(durations),
                "avg_ms": round(sum(durations) / len(durations), 3) if durations else 0.0,
                "min_ms": round(min(durations), 3) if durations else 0.0,
                "max_ms": round(max(durations), 3) if durations else 0.0,
                "total_tokens": s["total_tokens"],
            })
        result.sort(key=lambda x: x["call_count"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # メモリ使用量
    # ------------------------------------------------------------------

    def snapshot_memory(self, label: str = "") -> dict:
        """現在のメモリ使用量のスナップショットを記録する。

        psutil が利用できない環境では os モジュールのフォールバックを使用する。

        Args:
            label: スナップショットのラベル

        Returns:
            {"rss_mb": float, "vms_mb": float, "timestamp": str, "label": str}
        """
        if not self._enabled:
            return {}
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rss_mb = 0.0
        vms_mb = 0.0

        try:
            import psutil
            proc = psutil.Process(os.getpid())
            mem_info = proc.memory_info()
            rss_mb = round(mem_info.rss / (1024 * 1024), 2)
            vms_mb = round(mem_info.vms / (1024 * 1024), 2)
        except ImportError:
            # psutil が無い場合: /proc/self/status からRSSを取得する (Linux)
            try:
                with open("/proc/self/status", "r") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            rss_kb = int(line.split()[1])
                            rss_mb = round(rss_kb / 1024, 2)
                        elif line.startswith("VmSize:"):
                            vms_kb = int(line.split()[1])
                            vms_mb = round(vms_kb / 1024, 2)
            except (OSError, ValueError, IndexError):
                # どの方法でも取れなければ 0 のまま
                rss_mb = 0.0
                vms_mb = 0.0

        entry = {
            "rss_mb": rss_mb,
            "vms_mb": vms_mb,
            "label": label,
            "timestamp": now,
        }
        with self._data_lock:
            self._memory_snapshots.append(entry)
        return entry

    def get_memory_snapshots(self, limit: int = 50) -> list[dict]:
        """メモリスナップショット一覧を新しい順で返す。

        Args:
            limit: 取得件数上限

        Returns:
            [{"rss_mb": float, "vms_mb": float, "label": str, "timestamp": str}, ...]
        """
        with self._data_lock:
            data = list(self._memory_snapshots)
        data.reverse()
        return data[:limit]

    # ------------------------------------------------------------------
    # 総合レポート
    # ------------------------------------------------------------------

    def get_full_report(self) -> dict:
        """全プロファイルデータの総合レポートを返す。

        Returns:
            {
                "enabled": bool,
                "block_summary": [...],
                "api_summary": [...],
                "memory_latest": {...},
                "block_timings_count": int,
                "api_timings_count": int,
                "memory_snapshots_count": int,
            }
        """
        memory_snapshots = self.get_memory_snapshots(limit=1)
        return {
            "enabled": self._enabled,
            "block_summary": self.get_block_summary(),
            "api_summary": self.get_api_summary(),
            "memory_latest": memory_snapshots[0] if memory_snapshots else {},
            "block_timings_count": len(self._block_timings),
            "api_timings_count": len(self._api_timings),
            "memory_snapshots_count": len(self._memory_snapshots),
        }

    # ------------------------------------------------------------------
    # クリア
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """全プロファイルデータをクリアする。"""
        with self._data_lock:
            self._block_timings.clear()
            self._api_timings.clear()
            self._memory_snapshots.clear()
