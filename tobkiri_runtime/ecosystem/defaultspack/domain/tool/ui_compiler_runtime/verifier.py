from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.ui_compiler import BuildVerificationReport, RenderMatrix

from .npm_runner import NpmRunner


class ProjectVerifier:
    def __init__(self, *, npm_runner: NpmRunner | None = None) -> None:
        self.npm_runner = npm_runner or NpmRunner()

    def verify(
        self,
        *,
        workspace: Path,
        render_matrix: RenderMatrix,
        compression_report: dict[str, Any],
        run_build: bool = True,
    ) -> BuildVerificationReport:
        commands = self.npm_runner.run(workspace, run_build=run_build)
        command_status = {command["command"].rsplit(" ", 1)[-1]: command["status"] for command in commands}
        console_errors = sum(int(snapshot.metrics.get("consoleErrors") or 0) for snapshot in render_matrix.snapshots)
        horizontal_overflow = sum(1 for snapshot in render_matrix.snapshots if snapshot.metrics.get("horizontalOverflow"))
        return BuildVerificationReport(
            lint=_status(command_status.get("lint")),
            test=_status(command_status.get("test")),
            build=_status(command_status.get("build") if run_build else "passed"),
            render_matrix="passed" if render_matrix.snapshots else "failed",
            compression="passed" if compression_report.get("status") == "pass" else "failed",
            console_errors=console_errors,
            horizontal_overflow=horizontal_overflow,
            commands=commands,
        )


def _status(value: str | None) -> str:
    return value if value in {"passed", "failed", "missing-script"} else "failed"
