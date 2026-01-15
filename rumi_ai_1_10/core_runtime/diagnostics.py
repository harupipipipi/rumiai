"""
diagnostics.py - 起動/実行の結果集約(fail-softの"見える化")

Step1では「安定する器(構造)」を確定する。
内容の埋め方(ts生成やtrace短縮など)はStep2以降で強化してよい。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal


Status = Literal["success", "failed", "skipped", "disabled", "unknown"]


@dataclass
class Diagnostics:
    """
    起動・実行の診断情報を集約する。

    重要:
    - fail-softを採用する以上、失敗理由が追跡できることが最重要。
    - 各ステップ実行ごとに必ず record() される前提で設計する。
    """

    events: List[Dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _normalize_target(self, target: Any) -> Dict[str, Any]:
        """
        target は以下の形を推奨(必須ではない):
          {"kind": "none|pack|component", "id": <str|None>}
        互換のため、どんな入力でも安全に正規化する。
        """
        if isinstance(target, dict):
            kind = target.get("kind", "none")
            return {"kind": kind, "id": target.get("id")}
        if target is None:
            return {"kind": "none", "id": None}
        # 文字列などは id として扱う
        return {"kind": "unknown", "id": str(target)}

    def _normalize_error(self, error: Any) -> Optional[Dict[str, Any]]:
        """
        error は以下の形を推奨:
          {"type": "...", "message": "...", "trace": "...(optional)"}
        互換のため、例外オブジェクト/文字列/None を受ける。
        """
        if error is None:
            return None
        if isinstance(error, dict):
            # 最低限 type/message を確保
            return {
                "type": error.get("type", "Error"),
                "message": error.get("message", ""),
                **({} if "trace" not in error else {"trace": error.get("trace")}),
            }
        if isinstance(error, BaseException):
            return {"type": type(error).__name__, "message": str(error)}
        return {"type": "Error", "message": str(error)}

    def _normalize_status(self, status: Any) -> Status:
        if status in ("success", "failed", "skipped", "disabled", "unknown"):
            return status  # type: ignore[return-value]
        return "unknown"

    def normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        診断イベントを標準フォーマットへ正規化する。
        Kernel/拡張が"雑な形"で投げても、診断の信頼性を落とさない。
        """
        ev = dict(event or {})

        ts = ev.get("ts") or self._now_ts()
        phase = ev.get("phase") or "system"
        step_id = ev.get("step_id") or "unknown.step"
        handler = ev.get("handler") or "unknown.handler"
        status = self._normalize_status(ev.get("status"))
        target = self._normalize_target(ev.get("target"))
        error = self._normalize_error(ev.get("error"))
        meta = ev.get("meta")
        if not isinstance(meta, dict):
            meta = {"_raw_meta": meta} if meta is not None else {}

        return {
            "ts": ts,
            "phase": phase,
            "step_id": step_id,
            "handler": handler,
            "status": status,
            "target": target,
            "error": error,
            "meta": meta,
        }

    def record(self, event: Dict[str, Any]) -> None:
        """診断イベントを追加(正規化して保存)"""
        self.events.append(self.normalize_event(event))

    def record_step(
        self,
        *,
        phase: str,
        step_id: str,
        handler: str,
        status: Status,
        target: Any = None,
        error: Any = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """推奨：標準形で確実に記録するためのヘルパー"""
        self.record({
            "ts": self._now_ts(),
            "phase": phase,
            "step_id": step_id,
            "handler": handler,
            "status": status,
            "target": target,
            "error": error,
            "meta": meta or {},
        })

    def as_dict(self) -> Dict[str, Any]:
        """API返却などに使う辞書形式"""
        return {
            "started_at": self.started_at,
            "event_count": len(self.events),
            "events": list(self.events),
            "summary": self.summary(),
        }

    def summary(self) -> Dict[str, Any]:
        """
        サマリー(第1段階の"完璧"要件):
        - status別件数
        - phase別件数
        - failed一覧(直近の失敗を含む)
        - disabled一覧
        """
        counts: Dict[str, int] = {}
        phase_counts: Dict[str, int] = {}
        failed: List[Dict[str, Any]] = []
        disabled: List[Dict[str, Any]] = []

        last_event_ts: Optional[str] = None
        last_failure: Optional[Dict[str, Any]] = None

        for ev in self.events:
            status = ev.get("status", "unknown")
            phase = ev.get("phase", "system")

            counts[status] = counts.get(status, 0) + 1
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

            last_event_ts = ev.get("ts") or last_event_ts

            if status == "failed":
                item = {
                    "ts": ev.get("ts"),
                    "phase": phase,
                    "step_id": ev.get("step_id"),
                    "handler": ev.get("handler"),
                    "target": ev.get("target"),
                    "error": ev.get("error"),
                }
                failed.append(item)
                last_failure = item

            if status == "disabled":
                disabled.append({
                    "ts": ev.get("ts"),
                    "phase": phase,
                    "step_id": ev.get("step_id"),
                    "handler": ev.get("handler"),
                    "target": ev.get("target"),
                    "error": ev.get("error"),
                })

        return {
            "counts": counts,
            "phase_counts": phase_counts,
            "failed": failed[-50:],   # 大量化防止(直近のみ)
            "disabled": disabled[-50:],
            "last_event_ts": last_event_ts,
            "last_failure": last_failure,
        }
