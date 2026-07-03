from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any


RUNNING_STATUSES = {"running", "checking"}
TERMINAL_STATUSES = {"achieved", "failed", "blocked", "cancelled"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _gen_id() -> str:
    return str(uuid.uuid4())


class GoalStore:
    _instance = None

    def __new__(cls):
        path = cls._default_path()
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.path = path
            cls._instance._lock = threading.RLock()
            cls._instance._data = cls._instance._load()
            cls._instance._loaded_storage_signature = cls._instance._storage_signature()
        elif cls._instance.path != path:
            cls._instance.path = path
            cls._instance._data = cls._instance._load()
            cls._instance._loaded_storage_signature = cls._instance._storage_signature()
        return cls._instance

    @staticmethod
    def _default_path() -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_GOAL_STORE_PATH", "").strip()
        if override:
            return Path(override)
        return (
            Path(__file__).resolve().parents[2]
            / "user_data"
            / "shared"
            / "goals"
            / "runs.json"
        )

    def create_run(
        self,
        *,
        conversation_id: str,
        objective: str,
        checker_policy: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        objective = str(objective or "").strip()
        if not objective:
            raise ValueError("objective is required")
        conversation_id = str(conversation_id or "").strip()
        if not conversation_id:
            raise ValueError("conversation_id is required")
        now = _now_ms()
        run = {
            "goal_run_id": _gen_id(),
            "conversation_id": conversation_id,
            "objective": objective,
            "status": "running",
            "checker_policy": dict(checker_policy or {}),
            "last_checked_message_id": None,
            "latest_verdict": None,
            "created_at": now,
            "updated_at": now,
            "metadata": dict(metadata or {}),
            "event_log": [
                {
                    "event_id": _gen_id(),
                    "type": "goal.created",
                    "created_at": now,
                    "details": {"objective": objective},
                }
            ],
        }
        with self._lock:
            self._refresh_if_storage_changed()
            self._runs()[run["goal_run_id"]] = run
            self._save()
            return copy.deepcopy(run)

    def get_run(self, goal_run_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._refresh_if_storage_changed()
            run = self._runs().get(str(goal_run_id or "").strip())
            return copy.deepcopy(run) if isinstance(run, dict) else None

    def list_runs(
        self,
        *,
        conversation_id: str | None = None,
        statuses: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            self._refresh_if_storage_changed()
            runs = []
            for run in self._runs().values():
                if not isinstance(run, dict):
                    continue
                if conversation_id and str(run.get("conversation_id") or "") != conversation_id:
                    continue
                if statuses is not None and str(run.get("status") or "") not in statuses:
                    continue
                runs.append(copy.deepcopy(run))
            runs.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
            return runs

    def mark_check_started(
        self,
        goal_run_id: str,
        *,
        message_id: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            self._refresh_if_storage_changed()
            run = self._runs().get(str(goal_run_id or "").strip())
            if not isinstance(run, dict) or str(run.get("status") or "") not in RUNNING_STATUSES:
                return None
            run["status"] = "checking"
            run["updated_at"] = _now_ms()
            self._append_event_unlocked(
                run,
                "goal.check_started",
                {"message_id": str(message_id or "")},
            )
            self._save()
            return copy.deepcopy(run)

    def apply_checker_verdict(
        self,
        goal_run_id: str,
        verdict: dict[str, Any],
        *,
        message_id: str | None = None,
        internal: bool = False,
    ) -> dict[str, Any]:
        if not internal:
            raise PermissionError("only the isolated goal checker may write goal verdicts")
        with self._lock:
            self._refresh_if_storage_changed()
            run = self._runs().get(str(goal_run_id or "").strip())
            if not isinstance(run, dict):
                raise KeyError("goal run not found")
            if str(run.get("status") or "") in TERMINAL_STATUSES:
                return copy.deepcopy(run)
            normalized = normalize_verdict(verdict)
            run["latest_verdict"] = normalized
            if message_id:
                run["last_checked_message_id"] = str(message_id)
            run["status"] = _status_from_verdict(normalized)
            run["updated_at"] = _now_ms()
            self._append_event_unlocked(
                run,
                "goal.verdict",
                {"message_id": str(message_id or ""), "verdict": normalized},
            )
            self._save()
            return copy.deepcopy(run)

    def record_check_error(
        self,
        goal_run_id: str,
        message: str,
        *,
        message_id: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            self._refresh_if_storage_changed()
            run = self._runs().get(str(goal_run_id or "").strip())
            if not isinstance(run, dict) or str(run.get("status") or "") in TERMINAL_STATUSES:
                return None
            run["status"] = "running"
            if message_id:
                run["last_checked_message_id"] = str(message_id)
            run["updated_at"] = _now_ms()
            self._append_event_unlocked(
                run,
                "goal.check_error",
                {"message_id": str(message_id or ""), "message": str(message or "")},
            )
            self._save()
            return copy.deepcopy(run)

    def _runs(self) -> dict[str, dict[str, Any]]:
        runs = self._data.setdefault("runs", {})
        if not isinstance(runs, dict):
            runs = {}
            self._data["runs"] = runs
        return runs

    def _storage_signature(self) -> tuple[int, int] | None:
        try:
            stat = self.path.stat()
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def _refresh_if_storage_changed(self) -> None:
        current_signature = self._storage_signature()
        if getattr(self, "_loaded_storage_signature", None) == current_signature:
            return
        self._data = self._load()
        self._loaded_storage_signature = current_signature

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("schema_version", 1)
        data.setdefault("runs", {})
        return data

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = _now_ms()
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent),
            prefix="." + self.path.name + ".",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            tmp_path.replace(self.path)
            self._loaded_storage_signature = self._storage_signature()
        except BaseException:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise

    @staticmethod
    def _append_event_unlocked(
        run: dict[str, Any],
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        events = run.setdefault("event_log", [])
        if not isinstance(events, list):
            events = []
            run["event_log"] = events
        events.append(
            {
                "event_id": _gen_id(),
                "type": str(event_type or "goal.event"),
                "created_at": _now_ms(),
                "details": dict(details or {}),
            }
        )


def normalize_verdict(verdict: dict[str, Any] | None) -> dict[str, Any]:
    raw = verdict if isinstance(verdict, dict) else {}
    status = str(raw.get("status") or "").strip().lower()
    achieved = raw.get("achieved")
    if isinstance(achieved, bool):
        status = "achieved" if achieved else status
    if status not in {"running", "achieved", "failed", "blocked"}:
        status = "running"
    return {
        "status": status,
        "achieved": status == "achieved",
        "reason": str(raw.get("reason") or raw.get("summary") or "").strip(),
        "evidence": raw.get("evidence") if isinstance(raw.get("evidence"), list) else [],
        "next_check": str(raw.get("next_check") or "").strip(),
    }


def _status_from_verdict(verdict: dict[str, Any]) -> str:
    status = str(verdict.get("status") or "running").strip().lower()
    if status in {"achieved", "failed", "blocked"}:
        return status
    return "running"
