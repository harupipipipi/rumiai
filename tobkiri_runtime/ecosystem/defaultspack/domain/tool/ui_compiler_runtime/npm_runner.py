from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class NpmRunner:
    def run(self, workspace: Path, *, run_build: bool = True) -> list[dict[str, Any]]:
        package_json = workspace / "package.json"
        if not package_json.is_file():
            return [
                {"command": "npm run lint", "status": "missing-script", "reason": "package.json missing"},
                {"command": "npm run test", "status": "missing-script", "reason": "package.json missing"},
                {"command": "npm run build", "status": "missing-script", "reason": "package.json missing"},
            ]
        scripts = _scripts(package_json)
        commands = ["lint", "test", "build"] if run_build else ["lint", "test"]
        return [self._run_script(workspace, name, scripts) for name in commands]

    def _run_script(self, workspace: Path, script: str, scripts: dict[str, Any]) -> dict[str, Any]:
        command = f"npm run {script}"
        if script not in scripts:
            return {"command": command, "status": "missing-script", "exitCode": None, "stdout": "", "stderr": ""}
        try:
            completed = subprocess.run(
                ["npm", "run", script],
                cwd=str(workspace),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"command": command, "status": "failed", "exitCode": None, "stdout": "", "stderr": str(exc)}
        return {
            "command": command,
            "status": "passed" if completed.returncode == 0 else "failed",
            "exitCode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }


def _scripts(package_json: Path) -> dict[str, Any]:
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = payload.get("scripts")
    return scripts if isinstance(scripts, dict) else {}
