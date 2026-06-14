"""defaultspack_v2_soak — 24h soak test runner for self-improvement validation."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _timestamp_from_epoch(epoch_seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_seconds))


SOAK_RESULT_STATUSES = ("completed", "failed", "skipped")
LIVE_PRIVILEGED_OPT_IN_ENV = "RUMI_SOAK_ALLOW_LIVE_PRIVILEGED"
LIVE_ALLOWED_ROOT_ENV = "RUMI_SOAK_ALLOWED_WORKSPACE_ROOT"

SOAK_TASK_DEFINITIONS: list[dict[str, Any]] = [
    {
        "task_id": "soak_01_read_codebase",
        "title": "Read codebase and propose one tiny improvement",
        "category": "coding",
        "expected_outcome": "one file read, one improvement proposed",
        "tools_used": ["coding_file_read", "coding_file_search"],
    },
    {
        "task_id": "soak_02_add_test",
        "title": "Add or adjust one test",
        "category": "coding",
        "expected_outcome": "one test file created or modified",
        "tools_used": ["coding_file_read", "coding_file_write", "coding_file_patch"],
    },
    {
        "task_id": "soak_03_run_pytest",
        "title": "Run targeted pytest",
        "category": "coding",
        "expected_outcome": "pytest exit code 0",
        "tools_used": ["coding_terminal_exec"],
    },
    {
        "task_id": "soak_04_patch_file",
        "title": "Patch one file",
        "category": "coding",
        "expected_outcome": "one file patched",
        "tools_used": ["coding_file_patch"],
    },
    {
        "task_id": "soak_05_run_test_again",
        "title": "Run test again after patch",
        "category": "coding",
        "expected_outcome": "pytest exit code 0",
        "tools_used": ["coding_terminal_exec"],
    },
    {
        "task_id": "soak_06_commit_selected",
        "title": "Commit only selected path",
        "category": "coding",
        "expected_outcome": "commit with paths, unrelated dirty files remain",
        "tools_used": ["coding_git_commit", "coding_git_status"],
    },
    {
        "task_id": "soak_07_omni_vision",
        "title": "Use MiMo Omni to inspect UI screenshot",
        "category": "vision",
        "expected_outcome": "vision model describes screenshot content",
        "tools_used": ["browser_use"],
    },
    {
        "task_id": "soak_08_browser_interact",
        "title": "Use browser/computer tool to interact with webapp",
        "category": "browser",
        "expected_outcome": "browser interaction attempted, result classified",
        "tools_used": ["browser_use", "browser_computer"],
    },
    {
        "task_id": "soak_09_research_provider",
        "title": "Research provider/model info with official search",
        "category": "research",
        "expected_outcome": "provider info retrieved",
        "tools_used": ["web_search"],
    },
    {
        "task_id": "soak_10_update_knowledge",
        "title": "Update knowledge with findings",
        "category": "knowledge",
        "expected_outcome": "knowledge entry created or updated",
        "tools_used": ["rumi_api"],
    },
    {
        "task_id": "soak_11_spawn_subagent",
        "title": "Spawn subagent and verify handoff",
        "category": "agent",
        "expected_outcome": "subagent spawned, handoff recorded",
        "tools_used": ["subagent"],
    },
    {
        "task_id": "soak_12_summarize_friction",
        "title": "Summarize friction points",
        "category": "reporting",
        "expected_outcome": "friction summary produced",
        "tools_used": ["rumi_api"],
    },
]


class SoakTestRunner:
    """24h soak test runner for defaultspack v2 self-improvement validation."""

    def __init__(
        self,
        runtime,
        *,
        duration_hours: float = 24.0,
        state_path: str | Path | None = None,
        heartbeat_interval_seconds: int = 3600,
        stale_after_seconds: int = 7200,
    ) -> None:
        self.runtime = runtime
        self.duration_hours = duration_hours
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.stale_after_seconds = stale_after_seconds
        self._state_path = Path(state_path) if state_path else self._default_state_path()
        self._task_queue: list[dict[str, Any]] = []
        self._hourly_summaries: list[dict[str, Any]] = []

    def _default_state_path(self) -> Path:
        return self.runtime.workspace_root / "user_data" / "shared" / "soak_test" / "state.json"

    def load_task_queue(self) -> list[dict[str, Any]]:
        state = self._load_state()
        if state.get("task_queue"):
            return state["task_queue"]
        return list(SOAK_TASK_DEFINITIONS)

    def save_task_queue(self, tasks: list[dict[str, Any]]) -> None:
        state = self._load_state()
        state["task_queue"] = tasks
        self._save_state(state)

    def start_run(
        self,
        *,
        duration_hours: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self._load_state()
        now = time.time()
        state["runner_status"] = "running"
        state["started_at"] = _timestamp_from_epoch(now)
        state["started_at_epoch"] = now
        state["duration_hours"] = (
            duration_hours if duration_hours is not None else self.duration_hours
        )
        state["heartbeat_interval_seconds"] = self.heartbeat_interval_seconds
        state["stale_after_seconds"] = self.stale_after_seconds
        state.setdefault("task_queue", list(SOAK_TASK_DEFINITIONS))
        state.setdefault("results", [])
        state.setdefault("hourly_summaries", [])
        state.setdefault("lease_events", [])
        if metadata:
            state["metadata"] = metadata
        self._save_state(state)
        return state

    def record_heartbeat(self, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self._load_state()
        now = time.time()
        heartbeat = {
            "summary": summary or {},
            "timestamp": _timestamp_from_epoch(now),
            "epoch": now,
        }
        state["last_heartbeat_at"] = heartbeat["timestamp"]
        state["last_heartbeat_epoch"] = heartbeat["epoch"]
        heartbeats = state.setdefault("heartbeats", [])
        heartbeats.append(heartbeat)
        state["heartbeat_count"] = len(heartbeats)
        self._save_state(state)
        return heartbeat

    def claim_next_task(
        self,
        *,
        lease_seconds: int = 3600,
        now_epoch: float | None = None,
    ) -> dict[str, Any] | None:
        state = self._load_state()
        now = time.time() if now_epoch is None else now_epoch
        active = state.get("active_task")
        if active and float(active.get("lease_expires_epoch", 0)) > now:
            return active

        if active:
            events = state.setdefault("lease_events", [])
            events.append(
                {
                    "kind": "lease_expired",
                    "task_id": active.get("task_id"),
                    "timestamp": _timestamp_from_epoch(now),
                }
            )
            state["active_task"] = None

        queue = state.get("task_queue")
        if queue is None:
            queue = list(SOAK_TASK_DEFINITIONS)
            state["task_queue"] = queue
        if not queue:
            self._save_state(state)
            return None

        task = dict(queue[0])
        task["status"] = "running"
        task["lease_seconds"] = max(1, int(lease_seconds))
        task["started_at"] = _timestamp_from_epoch(now)
        task["started_at_epoch"] = now
        task["lease_expires_at"] = _timestamp_from_epoch(now + task["lease_seconds"])
        task["lease_expires_epoch"] = now + task["lease_seconds"]
        task["attempt"] = int(task.get("attempt", 0)) + 1
        if isinstance(queue, list) and queue:
            queue[0] = task
        state["active_task"] = task
        self._save_state(state)
        return task

    def record_task_result(
        self,
        task_id: str,
        *,
        status: str,
        model_role: str = "",
        model_id: str = "",
        tools_used: list[str] | None = None,
        files_read: list[str] | None = None,
        files_modified: list[str] | None = None,
        tests_run: int = 0,
        test_result: str = "",
        approval_events: int = 0,
        failures: list[str] | None = None,
        user_friction: str = "",
        next_recommendation: str = "",
    ) -> dict[str, Any]:
        if status not in SOAK_RESULT_STATUSES:
            raise ValueError(f"invalid soak task status: {status}")

        state = self._load_state()
        results = state.setdefault("results", [])
        result = {
            "task_id": task_id,
            "status": status,
            "model_role": model_role,
            "model_id": model_id,
            "tools_used": tools_used or [],
            "files_read": files_read or [],
            "files_modified": files_modified or [],
            "tests_run": tests_run,
            "test_result": test_result,
            "approval_events": approval_events,
            "failures": failures or [],
            "user_friction": user_friction,
            "next_recommendation": next_recommendation,
            "recorded_at": _timestamp(),
        }
        results.append(result)
        queue = state.get("task_queue")
        if isinstance(queue, list):
            state["task_queue"] = [task for task in queue if task.get("task_id") != task_id]
        active = state.get("active_task")
        if isinstance(active, dict) and active.get("task_id") == task_id:
            state["active_task"] = None
        self._save_state(state)
        return result

    def record_hourly_summary(self, summary: dict[str, Any]) -> None:
        state = self._load_state()
        summaries = state.setdefault("hourly_summaries", [])
        summaries.append({"summary": summary, "timestamp": _timestamp()})
        self._save_state(state)
        self.record_heartbeat(summary)

    def record_competitor_comparison(
        self,
        *,
        name: str,
        version: str = "",
        verified_with: list[str] | None = None,
        strengths: list[str] | None = None,
        gaps_for_rumi: list[str] | None = None,
    ) -> dict[str, Any]:
        state = self._load_state()
        comparison = {
            "name": name,
            "version": version,
            "verified_with": verified_with or [],
            "strengths": strengths or [],
            "gaps_for_rumi": gaps_for_rumi or [],
            "recorded_at": _timestamp(),
        }
        comparisons = state.setdefault("competitor_comparisons", [])
        comparisons.append(comparison)
        self._save_state(state)
        return comparison

    def run_claimed_dogfood_tasks(
        self,
        *,
        workspace_root: str | Path | None = None,
        task_count: int = 3,
        lease_seconds: int = 3600,
        state_path: str | Path | None = None,
        task_runner: Callable[..., dict[str, Any]] | None = None,
        refill_empty_queue: bool = True,
        dry_run: bool | None = None,
        allow_live_execution: bool = False,
        allowed_workspace_root: str | Path | None = None,
        approval_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run live dogfood tasks through the durable soak lease queue."""

        workspace = Path(workspace_root) if workspace_root else self.runtime.workspace_root
        if task_runner is None:
            live_policy = _live_execution_policy(
                workspace,
                allow_live_execution=allow_live_execution,
                allowed_workspace_root=allowed_workspace_root,
                approval_context=approval_context,
            )
            effective_dry_run = (not live_policy["allowed"]) if dry_run is None else bool(dry_run)
            if effective_dry_run or not live_policy["allowed"]:
                dry_run_reason = "dry_run requested" if effective_dry_run and live_policy["allowed"] else live_policy["reason"]

                def task_runner(**kwargs):
                    return _dry_run_task_result(reason=dry_run_reason, **kwargs)

            else:
                from domain.agent.self_improvement_live_loop import run_live_improvement

                def task_runner(**kwargs):
                    return run_live_improvement(**kwargs, approval_context=approval_context or {})

        live_state_path = (
            Path(state_path)
            if state_path
            else workspace / "user_data" / "shared" / "self_improvement" / "live_state.json"
        )

        results: list[dict[str, Any]] = []
        for _ in range(max(0, int(task_count))):
            claimed = self.claim_next_task(lease_seconds=lease_seconds)
            if claimed is None and refill_empty_queue:
                self.save_task_queue(list(SOAK_TASK_DEFINITIONS))
                claimed = self.claim_next_task(lease_seconds=lease_seconds)
            if claimed is None:
                break

            task_id = str(claimed.get("task_id", ""))
            result = self._run_claimed_task(
                task_runner=task_runner,
                workspace=workspace,
                state_path=live_state_path,
                claimed=claimed,
            )
            results.append(result)
            self.record_task_result(
                task_id,
                status="skipped" if result.get("dry_run") else "completed" if result.get("success") else "failed",
                model_role="main",
                model_id=str(result.get("model", "")),
                tools_used=list(claimed.get("tools_used") or []),
                files_read=list(result.get("files_read") or []),
                files_modified=list(result.get("files_modified") or []),
                test_result="pass" if result.get("test_exit_code") == 0 else "fail",
                failures=[str(result["error"])] if result.get("error") else [],
            )

        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]
        return {
            "total_tasks": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "dry_run": any(r.get("dry_run") for r in results),
            "results": results,
            "generated_at": _timestamp(),
        }

    def _run_claimed_task(
        self,
        *,
        task_runner: Callable[..., dict[str, Any]],
        workspace: Path,
        state_path: Path,
        claimed: dict[str, Any],
    ) -> dict[str, Any]:
        task_id = str(claimed.get("task_id", ""))
        task_title = str(claimed.get("title") or task_id)

        try:
            result = task_runner(
                workspace_root=workspace,
                task_id=task_id,
                task_title=task_title,
                state_path=state_path,
            )
        except Exception as exc:
            result = {"success": False, "task_id": task_id, "error": str(exc)}

        if not isinstance(result, dict):
            result = {
                "success": False,
                "task_id": task_id,
                "error": f"task runner returned {type(result).__name__}",
            }

        result = dict(result)
        result["task_id"] = task_id
        result["claimed_task_id"] = task_id
        result["lease_attempt"] = claimed.get("attempt", 1)
        result["lease_expires_at"] = claimed.get("lease_expires_at")
        return result

    def health_status(self, *, now_epoch: float | None = None) -> dict[str, Any]:
        state = self._load_state()
        now = time.time() if now_epoch is None else now_epoch
        reasons: list[str] = []

        started_at_epoch = state.get("started_at_epoch")
        heartbeat_epoch = state.get("last_heartbeat_epoch")
        if (
            started_at_epoch
            and not heartbeat_epoch
            and now - float(started_at_epoch) > self.stale_after_seconds
        ):
            reasons.append("no heartbeat recorded after stale threshold")
        if heartbeat_epoch and now - float(heartbeat_epoch) > self.stale_after_seconds:
            reasons.append("last heartbeat exceeded stale threshold")

        active = state.get("active_task")
        if isinstance(active, dict) and float(active.get("lease_expires_epoch", 0)) <= now:
            reasons.append("active task lease expired")

        results = state.get("results", [])
        failed = len([item for item in results if item.get("status") == "failed"])
        completed = len([item for item in results if item.get("status") == "completed"])
        total = len(results)
        if total > 0 and completed == 0 and failed == total:
            reasons.append("all recorded tasks failed")
        if total >= 3 and failed / total >= 0.5:
            reasons.append("failure rate exceeded 50 percent")
        if total >= 3 and completed == 0:
            reasons.append("no completed tasks after multiple attempts")

        status = "ok" if not reasons else "degraded"
        if total >= 3 and completed == 0:
            status = "down"

        return {
            "status": status,
            "reasons": reasons,
            "completed": completed,
            "failed": failed,
            "total_results": total,
            "active_task": active.get("task_id") if isinstance(active, dict) else None,
            "last_heartbeat_at": state.get("last_heartbeat_at"),
            "checked_at": _timestamp_from_epoch(now),
        }

    def generate_final_report(self) -> dict[str, Any]:
        state = self._load_state()
        results = state.get("results", [])
        completed = [r for r in results if r.get("status") == "completed"]
        failed = [r for r in results if r.get("status") == "failed"]
        friction = [r for r in results if r.get("user_friction")]
        return {
            "total_tasks": len(results),
            "completed": len(completed),
            "failed": len(failed),
            "friction_points": [
                {"task_id": r["task_id"], "friction": r["user_friction"]}
                for r in friction
            ],
            "hourly_summaries": state.get("hourly_summaries", []),
            "health": self.health_status(),
            "competitor_comparisons": state.get("competitor_comparisons", []),
            "generated_at": _timestamp(),
        }

    def can_resume(self) -> bool:
        state = self._load_state()
        return bool(state.get("task_queue"))

    def _load_state(self) -> dict[str, Any]:
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, **state, "updated_at": _timestamp()}
        self._state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _dry_run_task_result(*, reason: str, task_id: str, task_title: str, **_: Any) -> dict[str, Any]:
    return {
        "success": True,
        "dry_run": True,
        "dry_run_reason": reason,
        "task_id": task_id,
        "task_title": task_title,
        "model": "dry-run",
        "files_read": [],
        "files_modified": [],
        "test_exit_code": 0,
    }


def _live_execution_policy(
    workspace: Path,
    *,
    allow_live_execution: bool,
    allowed_workspace_root: str | Path | None,
    approval_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not (allow_live_execution and _truthy(os.environ.get(LIVE_PRIVILEGED_OPT_IN_ENV))):
        return {"allowed": False, "reason": "live privileged soak execution was not explicitly enabled"}
    if not (_truthy(os.environ.get("CI")) or _truthy(os.environ.get("GITHUB_ACTIONS"))):
        return {"allowed": False, "reason": "live privileged soak execution is CI-only"}

    root_value = allowed_workspace_root or os.environ.get(LIVE_ALLOWED_ROOT_ENV) or os.environ.get("GITHUB_WORKSPACE")
    if not root_value:
        return {"allowed": False, "reason": "live privileged soak execution requires an allowed workspace root"}
    if not _is_relative_to(workspace, Path(root_value)):
        return {"allowed": False, "reason": "workspace is outside the allowed live soak root"}

    if not _approval_context_allows_live_soak(approval_context):
        return {"allowed": False, "reason": "live privileged soak execution requires a server approval context"}
    return {"allowed": True, "reason": "live privileged soak execution enabled"}


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _approval_context_allows_live_soak(context: dict[str, Any] | None) -> bool:
    if not isinstance(context, dict):
        return False
    return (
        context.get("_tool_server_approval_token_valid") is True
        and context.get("_tool_server_approved") is True
    )
