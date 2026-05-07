from __future__ import annotations

import subprocess
from typing import Any

from core_runtime.runtime_events import utc_now


class SchedulerRunner:
    def run(self, job: dict[str, Any]) -> dict[str, Any]:
        if job.get("no_agent"):
            return self._run_script(job)
        return self._run_agent(job)

    def _run_script(self, job: dict[str, Any]) -> dict[str, Any]:
        script = job.get("script")
        if not script:
            return {"status": "error", "error": "script is required for no_agent job", "created_at": utc_now()}
        completed = subprocess.run(
            str(script),
            shell=True,
            capture_output=True,
            text=True,
            timeout=int(job.get("timeout_seconds") or 60),
        )
        return {
            "status": "completed" if completed.returncode == 0 else "failed",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
            "created_at": utc_now(),
        }

    def _run_agent(self, job: dict[str, Any]) -> dict[str, Any]:
        from domain.agent.engine import AgentEngine

        context = {
            "agent_id": job.get("agent_id", "main"),
            "runtime_profile_key": job.get("runtime_profile_key") or None,
            "session_key": f"cron:{job.get('job_id')}",
            "scheduler_job_id": job.get("job_id"),
        }
        result = AgentEngine().execute(
            job.get("prompt", ""),
            [],
            job.get("model", "default"),
            job.get("system_prompt"),
            context,
        )
        return {"status": result.get("status"), "agent_result": result, "created_at": utc_now()}
