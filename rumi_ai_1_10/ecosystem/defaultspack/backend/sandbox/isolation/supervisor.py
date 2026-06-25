from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from ..errors import (
    SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE,
    SANDBOX_RUNTIME_UNAVAILABLE,
)
from .bubblewrap_builder import build_bubblewrap_argv
from .cgroup import build_systemd_run_argv
from .spec import BubblewrapSandboxSpec, CgroupLimits, WorkspaceMount


MAX_SANDBOX_OUTPUT_BYTES = 1024 * 1024


class ManagedSandboxSupervisor:
    """Execute untrusted functions inside Bubblewrap plus a systemd cgroup."""

    def __init__(self, provider_registry: Any | None = None) -> None:
        self.provider_registry = provider_registry

    def available(self) -> bool:
        return shutil.which("bwrap") is not None and shutil.which("systemd-run") is not None

    def execute_capability(self, request: dict[str, Any]) -> dict[str, Any]:
        if shutil.which("bwrap") is None:
            return self._unavailable(request, "Managed Bubblewrap sandbox runtime is unavailable")
        if shutil.which("systemd-run") is None:
            return self._unavailable(
                request,
                "Managed cgroup resource controller is unavailable",
                error_type=SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE,
            )

        timeout = _bounded_timeout(request.get("timeout_seconds"))
        sandbox_id = _sandbox_id(request)
        with tempfile.TemporaryDirectory(prefix=f"{sandbox_id}-") as tmp:
            temp_root = Path(tmp)
            workspace = temp_root / "workspace"
            function_target = workspace / "function"
            workspace.mkdir(mode=0o700)

            module_rel, callable_name = self._stage_function(
                request=request,
                function_target=function_target,
            )
            runner_path = self._stage_runner(request, workspace)
            input_path = workspace / "input.json"
            input_path.write_text(
                _runner_payload(
                    module_path=f"/workspace/function/{module_rel.as_posix()}",
                    callable_name=callable_name,
                    context=request.get("context") if isinstance(request.get("context"), dict) else {},
                    args=request.get("args") if isinstance(request.get("args"), dict) else {},
                ),
                encoding="utf-8",
            )

            immutable_root = _immutable_root(request)
            seccomp_fd = None
            pass_fds: tuple[int, ...] = ()
            seccomp_profile = str(request.get("seccomp_profile") or "").strip()
            try:
                if seccomp_profile:
                    seccomp_fd = os.open(Path(seccomp_profile), os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
                    pass_fds = (seccomp_fd,)
                spec = BubblewrapSandboxSpec(
                    sandbox_id=sandbox_id,
                    profile_id=str(request.get("profile_runtime") or request.get("principal_id") or "default"),
                    immutable_root=immutable_root,
                    workspace=WorkspaceMount(source=workspace, read_only=False),
                    argv=("python3", f"/workspace/{runner_path.name}", "--input-file", "/workspace/input.json"),
                    env={
                        "RUMI_PROFILE_RUNTIME": str(request.get("profile_runtime") or ""),
                    },
                    network_enabled=False,
                    seccomp_fd=seccomp_fd,
                )
                bwrap_argv = build_bubblewrap_argv(spec)
                unit_name = f"rumi-sandbox-{sandbox_id}"
                command = build_systemd_run_argv(
                    unit_name,
                    CgroupLimits(runtime_max_sec=int(timeout)),
                    bwrap_argv,
                )
                proc = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=timeout + 2,
                    close_fds=True,
                    pass_fds=pass_fds,
                )
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "ok": False,
                    "error": "Managed sandbox execution timed out",
                    "error_type": "timeout",
                    "execution_boundary": "managed_sandbox",
                }
            finally:
                if seccomp_fd is not None:
                    try:
                        os.close(seccomp_fd)
                    except OSError:
                        pass

            return self._response_from_process(proc)

    def _stage_function(self, *, request: dict[str, Any], function_target: Path) -> tuple[Path, str]:
        function_dir = _required_dir(request.get("function_dir"), "function_dir")
        main_py_path = request.get("main_py_path")
        entrypoint = str(request.get("entrypoint") or "main.py:run")
        entry_file, callable_name = (
            entrypoint.rsplit(":", 1) if ":" in entrypoint else (entrypoint, "run")
        )
        if main_py_path:
            main_path = Path(str(main_py_path)).expanduser().resolve()
        else:
            main_path = (function_dir / entry_file).resolve()
        try:
            module_rel = main_path.relative_to(function_dir)
        except ValueError as exc:
            raise ValueError("Sandbox function entrypoint escapes function directory") from exc
        if not main_path.is_file():
            raise ValueError("Sandbox function entrypoint not found")
        shutil.copytree(function_dir, function_target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return module_rel, callable_name or "run"

    def _stage_runner(self, request: dict[str, Any], workspace: Path) -> Path:
        source = _required_file(request.get("runner_path"), "runner_path")
        target = workspace / "function_runner.py"
        shutil.copy2(source, target)
        return target

    def _response_from_process(self, proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        stdout = proc.stdout or ""
        stderr = (proc.stderr or "").strip()
        if len(stdout.encode("utf-8")) > MAX_SANDBOX_OUTPUT_BYTES:
            return {
                "success": False,
                "ok": False,
                "error": "Managed sandbox response too large",
                "error_type": "response_too_large",
                "execution_boundary": "managed_sandbox",
            }
        output = stdout.strip()
        parsed: Any = None
        if output:
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "ok": False,
                    "error": "Managed sandbox output is not valid JSON",
                    "error_type": "invalid_json_output",
                    "execution_boundary": "managed_sandbox",
                }
        if proc.returncode != 0:
            if isinstance(parsed, dict) and parsed.get("error"):
                error_text = str(parsed.get("error") or "")
                error_type = str(parsed.get("error_type") or "function_execution_error")
            else:
                error_text = f"Managed sandbox exited {proc.returncode}: {stderr}"[:1000]
                error_type = "function_execution_error"
            return {
                "success": False,
                "ok": False,
                "error": error_text,
                "error_type": error_type,
                "execution_boundary": "managed_sandbox",
            }
        return {
            "success": True,
            "ok": True,
            "output": parsed,
            "execution_boundary": "managed_sandbox",
        }

    def _unavailable(
        self,
        request: dict[str, Any],
        message: str,
        *,
        error_type: str = SANDBOX_RUNTIME_UNAVAILABLE,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "ok": False,
            "error": message,
            "error_type": error_type,
            "execution_boundary": "managed_sandbox",
            "request": {
                "profile_runtime": request.get("profile_runtime"),
                "pack_id": request.get("pack_id"),
                "function_id": request.get("function_id"),
                "calling_convention": request.get("calling_convention"),
            },
        }


def _runner_payload(*, module_path: str, callable_name: str, context: dict[str, Any], args: dict[str, Any]) -> str:
    return json.dumps(
        {
            "module_path": module_path,
            "callable_name": callable_name,
            "context": context,
            "args": args,
        },
        ensure_ascii=False,
        default=str,
    )


def _sandbox_id(request: dict[str, Any]) -> str:
    raw = str(request.get("sandbox_id") or "").strip()
    if raw and "/" not in raw and "\x00" not in raw:
        return raw
    return "sbx_" + uuid.uuid4().hex[:24]


def _bounded_timeout(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 60.0
    return min(max(parsed, 1.0), 60.0)


def _immutable_root(request: dict[str, Any]) -> Path:
    raw = (
        request.get("immutable_root")
        or os.environ.get("RUMI_SANDBOX_IMMUTABLE_ROOT")
        or "/"
    )
    return _required_dir(raw, "immutable_root")


def _required_dir(value: Any, label: str) -> Path:
    path = Path(str(value or "")).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"{label} must be an existing directory")
    return path


def _required_file(value: Any, label: str) -> Path:
    path = Path(str(value or "")).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{label} must be an existing file")
    return path
