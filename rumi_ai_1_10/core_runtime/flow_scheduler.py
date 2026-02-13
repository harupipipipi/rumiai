"""
flow_scheduler.py - Flow スケジュール実行エンジン

cron式またはinterval秒で定期的にFlowを実行するスケジューラー。
threading.Timer ベースの tick 方式で10秒ごとにスケジュールテーブルを評価する。

設計原則:
- 外部ライブラリ不使用（標準ライブラリのみ）
- Kernel への直接参照なし（コールバック経由で疎結合）
- 実行中の Flow は重複実行しない
- グレースフル shutdown 対応
- cron: 5フィールド（分 時 日 月 曜日）、*, */N, 数値, カンマ区切り, 範囲をサポート
- interval: 最小10秒
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set


# tick 間隔（秒）
TICK_INTERVAL = 10.0

# interval の最小値（秒）
MIN_INTERVAL = 10.0


class CronField:
    """cron の1フィールドを表現する。"""

    __slots__ = ("_values",)

    def __init__(self, values: frozenset):
        self._values = values

    def matches(self, value: int) -> bool:
        return value in self._values

    @classmethod
    def parse(cls, expr: str, min_val: int, max_val: int) -> "CronField":
        """
        cron フィールド式をパースする。

        サポート:
        - * (全値)
        - */N (ステップ)
        - N (単一値)
        - N,M,... (カンマ区切り)
        - N-M (範囲)
        - N-M/S (範囲+ステップ)
        """
        values: set = set()

        for part in expr.split(","):
            part = part.strip()
            if not part:
                continue

            if part == "*":
                values.update(range(min_val, max_val + 1))
            elif part.startswith("*/"):
                step_str = part[2:]
                step = int(step_str)
                if step <= 0:
                    raise ValueError(f"Invalid step: {part}")
                values.update(range(min_val, max_val + 1, step))
            elif "-" in part and "/" in part:
                # N-M/S 形式
                range_part, step_str = part.split("/", 1)
                start_str, end_str = range_part.split("-", 1)
                start, end, step = int(start_str), int(end_str), int(step_str)
                if step <= 0:
                    raise ValueError(f"Invalid step: {part}")
                values.update(range(start, end + 1, step))
            elif "-" in part:
                # N-M 形式
                start_str, end_str = part.split("-", 1)
                start, end = int(start_str), int(end_str)
                values.update(range(start, end + 1))
            else:
                values.add(int(part))

        # 範囲バリデーション
        for v in values:
            if v < min_val or v > max_val:
                raise ValueError(
                    f"Value {v} out of range [{min_val}, {max_val}]"
                )

        return cls(frozenset(values))


class CronExpression:
    """5フィールドの cron 式を表現する。"""

    __slots__ = ("minute", "hour", "day", "month", "weekday", "_raw")

    def __init__(
        self,
        minute: CronField,
        hour: CronField,
        day: CronField,
        month: CronField,
        weekday: CronField,
        raw: str = "",
    ):
        self.minute = minute
        self.hour = hour
        self.day = day
        self.month = month
        self.weekday = weekday
        self._raw = raw

    def matches(self, dt: datetime) -> bool:
        """datetime が cron 式にマッチするか判定する。"""
        return (
            self.minute.matches(dt.minute)
            and self.hour.matches(dt.hour)
            and self.day.matches(dt.day)
            and self.month.matches(dt.month)
            and self.weekday.matches(dt.weekday())
        )

    @classmethod
    def parse(cls, cron_str: str) -> "CronExpression":
        """
        5フィールドの cron 式をパースする。

        weekday の変換:
        - cron: 0=Sun, 1=Mon, ..., 6=Sat
        - Python datetime.weekday(): 0=Mon, ..., 6=Sun
        - 変換式: python_val = (cron_val - 1) % 7
        """
        fields = cron_str.strip().split()
        if len(fields) != 5:
            raise ValueError(
                f"Cron expression must have 5 fields, got {len(fields)}: '{cron_str}'"
            )

        minute = CronField.parse(fields[0], 0, 59)
        hour = CronField.parse(fields[1], 0, 23)
        day = CronField.parse(fields[2], 1, 31)
        month = CronField.parse(fields[3], 1, 12)

        # weekday: cron 0=Sun -> Python 6, cron 1=Mon -> Python 0, etc.
        raw_weekday = CronField.parse(fields[4], 0, 6)
        converted_values: set = set()
        for v in raw_weekday._values:
            converted_values.add((v - 1) % 7)
        weekday = CronField(frozenset(converted_values))

        return cls(minute, hour, day, month, weekday, raw=cron_str)


class ScheduleEntry:
    """スケジュールテーブルの1エントリ。"""

    __slots__ = (
        "flow_id",
        "cron",
        "interval_seconds",
        "last_executed_at",
        "next_interval_at",
        "_last_cron_minute",
    )

    def __init__(
        self,
        flow_id: str,
        cron: Optional[CronExpression] = None,
        interval_seconds: Optional[float] = None,
    ):
        self.flow_id = flow_id
        self.cron = cron
        self.interval_seconds = interval_seconds
        self.last_executed_at: float = 0.0  # monotonic
        self.next_interval_at: float = 0.0  # monotonic
        self._last_cron_minute: int = -1  # 同一分内での多重発火防止

    def should_run(self, now_mono: float, now_dt: datetime) -> bool:
        """今の tick で実行すべきか判定する。"""
        if self.cron is not None:
            # 同一分内で多重発火しないようにする
            current_minute = now_dt.year * 525960 + now_dt.month * 43800 + \
                now_dt.day * 1440 + now_dt.hour * 60 + now_dt.minute
            if current_minute == self._last_cron_minute:
                return False
            if self.cron.matches(now_dt):
                self._last_cron_minute = current_minute
                return True
            return False
        if self.interval_seconds is not None:
            return now_mono >= self.next_interval_at
        return False


class FlowScheduler:
    """
    Flow スケジューラー。

    tick ベース（TICK_INTERVAL 秒ごと）で全スケジュールエントリを評価し、
    実行条件を満たした Flow をコールバック経由で実行する。

    Kernel を直接参照しない疎結合設計。
    """

    def __init__(
        self,
        execute_callback: Callable[[str, Optional[Dict[str, Any]]], Dict[str, Any]],
        diagnostics_callback: Optional[Callable[..., None]] = None,
    ):
        """
        Args:
            execute_callback: Flow 実行コールバック。
                シグネチャ: (flow_id, context) -> result_dict
                典型的には kernel.execute_flow_sync を渡す。
            diagnostics_callback: 診断記録コールバック（任意）。
                シグネチャ: (phase=, step_id=, handler=, status=, **kwargs)
        """
        self._execute_callback = execute_callback
        self._diagnostics_callback = diagnostics_callback
        self._entries: Dict[str, ScheduleEntry] = {}
        self._running_flows: Set[str] = set()
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._stopped = threading.Event()
        self._stopped.set()  # 初期状態は停止
        self._executor: Optional[Any] = None  # ThreadPoolExecutor

    def register(
        self,
        flow_id: str,
        schedule_def: Dict[str, Any],
    ) -> bool:
        """
        スケジュールエントリを登録する。

        Args:
            flow_id: Flow ID
            schedule_def: {'cron': '...'} or {'interval': N}

        Returns:
            登録成功したか
        """
        cron_expr = schedule_def.get("cron")
        interval = schedule_def.get("interval")

        if not cron_expr and not interval:
            return False

        cron = None
        interval_seconds = None

        if cron_expr:
            try:
                cron = CronExpression.parse(str(cron_expr))
            except ValueError as e:
                self._diag(
                    "scheduler",
                    f"scheduler.register.{flow_id}.failed",
                    "flow_scheduler:register",
                    "failed",
                    error=str(e),
                )
                return False

        if interval:
            interval_seconds = max(float(interval), MIN_INTERVAL)

        entry = ScheduleEntry(
            flow_id=flow_id,
            cron=cron,
            interval_seconds=interval_seconds,
        )

        with self._lock:
            # interval の初回実行を interval_seconds 後に設定
            if interval_seconds is not None:
                entry.next_interval_at = time.monotonic() + interval_seconds
            self._entries[flow_id] = entry

        self._diag(
            "scheduler",
            f"scheduler.register.{flow_id}",
            "flow_scheduler:register",
            "success",
            meta={
                "flow_id": flow_id,
                "cron": cron_expr,
                "interval": interval_seconds,
            },
        )
        return True

    def unregister(self, flow_id: str) -> bool:
        """スケジュールエントリを削除する。"""
        with self._lock:
            if flow_id in self._entries:
                del self._entries[flow_id]
                return True
        return False

    def start(self) -> None:
        """スケジューラーを開始する。"""
        if not self._stopped.is_set():
            return  # 既に起動中

        from concurrent.futures import ThreadPoolExecutor
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="flow_sched"
        )
        self._stopped.clear()
        self._schedule_next_tick()

        self._diag(
            "scheduler",
            "scheduler.start",
            "flow_scheduler:start",
            "success",
            meta={"entry_count": len(self._entries)},
        )

    def stop(self, timeout: float = 30.0) -> None:
        """スケジューラーをグレースフル停止する。"""
        self._stopped.set()

        # Timer をキャンセル
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

        # ThreadPoolExecutor を shutdown
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=False)
            self._executor = None

        self._diag(
            "scheduler",
            "scheduler.stop",
            "flow_scheduler:stop",
            "success",
        )

    def get_status(self) -> Dict[str, Any]:
        """現在のスケジューラー状態を返す。"""
        with self._lock:
            return {
                "running": not self._stopped.is_set(),
                "entries": {
                    fid: {
                        "cron": entry.cron._raw if entry.cron else None,
                        "interval": entry.interval_seconds,
                        "last_executed_at": entry.last_executed_at,
                        "is_running": fid in self._running_flows,
                    }
                    for fid, entry in self._entries.items()
                },
            }

    def _schedule_next_tick(self) -> None:
        """次の tick をスケジュールする。"""
        if self._stopped.is_set():
            return
        self._timer = threading.Timer(TICK_INTERVAL, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        """tick 処理: スケジュールテーブルを評価し、条件を満たしたFlowを実行。"""
        if self._stopped.is_set():
            return

        now_mono = time.monotonic()
        now_dt = datetime.now(timezone.utc)

        with self._lock:
            entries_snapshot = list(self._entries.values())

        for entry in entries_snapshot:
            if self._stopped.is_set():
                break

            # 重複実行防止
            with self._lock:
                if entry.flow_id in self._running_flows:
                    continue

            if entry.should_run(now_mono, now_dt):
                with self._lock:
                    # ダブルチェック
                    if entry.flow_id in self._running_flows:
                        continue
                    self._running_flows.add(entry.flow_id)
                    entry.last_executed_at = now_mono
                    if entry.interval_seconds is not None:
                        entry.next_interval_at = now_mono + entry.interval_seconds

                # executor に submit
                if self._executor is not None:
                    self._executor.submit(self._execute_flow, entry.flow_id)

        # 次の tick をスケジュール
        self._schedule_next_tick()

    def _execute_flow(self, flow_id: str) -> None:
        """Flow を実行する（ワーカースレッド）。"""
        try:
            self._diag(
                "scheduler",
                f"scheduler.execute.{flow_id}.start",
                "flow_scheduler:execute",
                "success",
                meta={"flow_id": flow_id},
            )

            result = self._execute_callback(flow_id, {"_triggered_by": "scheduler"})

            status = "success"
            if isinstance(result, dict) and result.get("_error"):
                status = "failed"

            self._diag(
                "scheduler",
                f"scheduler.execute.{flow_id}.done",
                "flow_scheduler:execute",
                status,
                meta={"flow_id": flow_id, "has_error": status == "failed"},
            )

        except Exception as e:
            self._diag(
                "scheduler",
                f"scheduler.execute.{flow_id}.error",
                "flow_scheduler:execute",
                "failed",
                error=e,
            )
        finally:
            with self._lock:
                self._running_flows.discard(flow_id)

    def _diag(
        self,
        phase: str,
        step_id: str,
        handler: str,
        status: str,
        error: Any = None,
        meta: Any = None,
    ) -> None:
        """診断記録を行う。"""
        if self._diagnostics_callback is not None:
            try:
                kwargs: Dict[str, Any] = {
                    "phase": phase,
                    "step_id": step_id,
                    "handler": handler,
                    "status": status,
                }
                if error is not None:
                    kwargs["error"] = error
                if meta is not None:
                    kwargs["meta"] = meta
                self._diagnostics_callback(**kwargs)
            except Exception:
                pass


def scan_flows_for_schedules(
    interface_registry: Any,
) -> List[Dict[str, Any]]:
    """
    InterfaceRegistry から全 Flow を走査し、schedule フィールドを持つものを返す。

    Returns:
        [{"flow_id": "...", "schedule": {...}}, ...]
    """
    results: List[Dict[str, Any]] = []
    try:
        all_entries = interface_registry.list() or {}
        for key in all_entries:
            if not key.startswith("flow."):
                continue
            if key.startswith("flow.hooks") or key.startswith("flow.construct"):
                continue
            flow_id = key[5:]  # "flow." を除去
            flow_def = interface_registry.get(key, strategy="last")
            if isinstance(flow_def, dict) and "schedule" in flow_def:
                schedule = flow_def["schedule"]
                if isinstance(schedule, dict):
                    results.append({
                        "flow_id": flow_id,
                        "schedule": schedule,
                    })
    except Exception:
        pass
    return results
