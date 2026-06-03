#!/usr/bin/env python3
"""Smoke-test package installation from a built wheel.

The check intentionally runs outside the repository after installation. This
guards the public first-run path that new users and release reviewers will try.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def console_script(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def command_result(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "args": proc.args,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def fail(message: str, proc: subprocess.CompletedProcess[str] | None = None) -> int:
    payload: dict[str, Any] = {"status": "fail", "error": message}
    if proc is not None:
        payload["command"] = command_result(proc)
    print(json.dumps(payload, indent=2))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the temporary wheel and virtualenv directories for debugging.",
    )
    ns = parser.parse_args()

    temp_root = Path(tempfile.mkdtemp(prefix="rumi-package-smoke-"))
    try:
        wheel_dir = temp_root / "wheelhouse"
        install_dir = temp_root / "install-venv"
        run_dir = temp_root / "outside-checkout"
        wheel_dir.mkdir()
        run_dir.mkdir()

        build = run(
            [sys.executable, "-m", "pip", "wheel", ".", "-w", str(wheel_dir), "--no-deps"],
            cwd=ROOT,
        )
        if build.returncode != 0:
            return fail("wheel build failed", build)

        wheels = sorted(wheel_dir.glob("rumi_ai-*.whl"))
        if len(wheels) != 1:
            return fail(f"expected one rumi_ai wheel, found {len(wheels)}")
        wheel = wheels[0]

        venv.EnvBuilder(with_pip=True).create(install_dir)
        py = venv_python(install_dir)

        upgrade = run([str(py), "-m", "pip", "install", "--upgrade", "pip"], cwd=run_dir)
        if upgrade.returncode != 0:
            return fail("pip upgrade failed", upgrade)

        install = run([str(py), "-m", "pip", "install", str(wheel)], cwd=run_dir)
        if install.returncode != 0:
            return fail("wheel install failed", install)

        module_health = run([str(py), "-m", "rumi_ai", "--health"], cwd=run_dir)
        if module_health.returncode != 0:
            return fail("module health check failed", module_health)

        script_health = run([str(console_script(install_dir, "rumi-ai")), "--health"], cwd=run_dir)
        if script_health.returncode != 0:
            return fail("console script health check failed", script_health)

        payload = {
            "status": "pass",
            "wheel": str(wheel),
            "run_dir": str(run_dir),
            "checks": {
                "module_health": command_result(module_health),
                "console_script_health": command_result(script_health),
            },
        }
        print(json.dumps(payload, indent=2))
        return 0
    finally:
        if ns.keep_temp:
            print(f"kept temp directory: {temp_root}", file=sys.stderr)
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
