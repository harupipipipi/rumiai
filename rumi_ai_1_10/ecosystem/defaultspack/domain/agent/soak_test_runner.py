"""defaultspack_v2_soak — 24h soak test runner for self-improvement validation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
    ) -> None:
        self.runtime = runtime
        self.duration_hours = duration_hours
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
        self._save_state(state)
        return result

    def record_hourly_summary(self, summary: dict[str, Any]) -> None:
        state = self._load_state()
        summaries = state.setdefault("hourly_summaries", [])
        summaries.append({"summary": summary, "timestamp": _timestamp()})
        self._save_state(state)

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
