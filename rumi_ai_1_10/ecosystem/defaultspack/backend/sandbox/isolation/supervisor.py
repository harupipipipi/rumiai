from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
import stat
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
MAX_STAGE_FILES = 1024
MAX_STAGE_TOTAL_BYTES = 16 * 1024 * 1024
MAX_STAGE_FILE_BYTES = 2 * 1024 * 1024
SANDBOX_ROOT_MARKER = ".rumi-sandbox-root"


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

            module_rel, callable_name, stage_audit = self._stage_function(
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
            seccomp_profile = str(request.get("seccomp_profile") or "").strip()
            try:
                seccomp_profile_path = _required_file(seccomp_profile, "seccomp_profile") if seccomp_profile else None
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
                )
                bwrap_argv = build_bubblewrap_argv(spec)
                sandbox_command, stdout_path, stderr_path, returncode_path = _sandbox_wrapper_command(
                    temp_root=temp_root,
                    bwrap_argv=bwrap_argv,
                    seccomp_profile=seccomp_profile_path,
                )
                unit_name = f"rumi-sandbox-{sandbox_id}"
                command = build_systemd_run_argv(
                    unit_name,
                    CgroupLimits(runtime_max_sec=int(timeout)),
                    sandbox_command,
                )
                systemd_proc = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=timeout + 2,
                    close_fds=True,
                )
                proc = _completed_from_wrapper_files(
                    command=command,
                    systemd_proc=systemd_proc,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    returncode_path=returncode_path,
                )
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "ok": False,
                    "error": "Managed sandbox execution timed out",
                    "error_type": "timeout",
                    "execution_boundary": "managed_sandbox",
                }

            return self._response_from_process(proc, stage_audit=stage_audit)

    def _stage_function(self, *, request: dict[str, Any], function_target: Path) -> tuple[Path, str, dict[str, int]]:
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
        stage_audit = _stage_regular_tree(function_dir, function_target)
        return module_rel, callable_name or "run", stage_audit

    def _stage_runner(self, request: dict[str, Any], workspace: Path) -> Path:
        source = _required_file(request.get("runner_path"), "runner_path")
        target = workspace / "function_runner.py"
        shutil.copy2(source, target)
        return target

    def _response_from_process(self, proc: subprocess.CompletedProcess[str], *, stage_audit: dict[str, int] | None = None) -> dict[str, Any]:
        stdout = proc.stdout or ""
        stderr = (proc.stderr or "").strip()
        if len(stdout.encode("utf-8")) > MAX_SANDBOX_OUTPUT_BYTES:
            return {
                "success": False,
                "ok": False,
                "error": "Managed sandbox response too large",
                "error_type": "response_too_large",
                "execution_boundary": "managed_sandbox",
                "sandbox_stage": dict(stage_audit or {}),
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
                    "sandbox_stage": dict(stage_audit or {}),
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
                "sandbox_stage": dict(stage_audit or {}),
            }
        return {
            "success": True,
            "ok": True,
            "output": parsed,
            "execution_boundary": "managed_sandbox",
            "sandbox_stage": dict(stage_audit or {}),
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


def _sandbox_wrapper_command(
    *,
    temp_root: Path,
    bwrap_argv: list[str],
    seccomp_profile: Path | None,
) -> tuple[list[str], Path, Path, Path]:
    wrapper = temp_root / "run_bwrap_with_seccomp.py"
    argv_file = temp_root / "bwrap_argv.json"
    stdout_path = temp_root / "sandbox.stdout"
    stderr_path = temp_root / "sandbox.stderr"
    returncode_path = temp_root / "sandbox.returncode"
    argv_file.write_text(
        json.dumps(
            {
                "argv": bwrap_argv,
                "seccomp_profile": str(seccomp_profile) if seccomp_profile is not None else "",
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "returncode_path": str(returncode_path),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    wrapper.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "import os",
                "import subprocess",
                "import sys",
                "payload = json.load(open(sys.argv[1], encoding='utf-8'))",
                "argv = list(payload['argv'])",
                "pass_fds = ()",
                "profile = str(payload.get('seccomp_profile') or '')",
                "if profile:",
                "    fd = os.open(profile, os.O_RDONLY)",
                "    os.set_inheritable(fd, True)",
                "    pass_fds = (fd,)",
                "    try:",
                "        index = argv.index('--')",
                "    except ValueError:",
                "        index = len(argv)",
                "    argv[index:index] = ['--seccomp', str(fd)]",
                "with open(payload['stdout_path'], 'wb') as out, open(payload['stderr_path'], 'wb') as err:",
                "    proc = subprocess.run(argv, stdout=out, stderr=err, close_fds=True, pass_fds=pass_fds)",
                "open(payload['returncode_path'], 'w', encoding='utf-8').write(str(proc.returncode))",
                "raise SystemExit(proc.returncode)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    os.chmod(wrapper, 0o700)
    os.chmod(argv_file, 0o600)
    return [sys.executable, str(wrapper), str(argv_file)], stdout_path, stderr_path, returncode_path


def _completed_from_wrapper_files(
    *,
    command: list[str],
    systemd_proc: subprocess.CompletedProcess[str],
    stdout_path: Path,
    stderr_path: Path,
    returncode_path: Path,
) -> subprocess.CompletedProcess[str]:
    if not returncode_path.is_file():
        return subprocess.CompletedProcess(
            command,
            systemd_proc.returncode,
            stdout=systemd_proc.stdout,
            stderr=systemd_proc.stderr,
        )
    try:
        returncode = int(returncode_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        returncode = systemd_proc.returncode
    stdout = _read_text_if_present(stdout_path, fallback=systemd_proc.stdout)
    stderr = _read_text_if_present(stderr_path, fallback=systemd_proc.stderr)
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


def _read_text_if_present(path: Path, *, fallback: str | None = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return fallback or ""


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
    raw = request.get("immutable_root") or os.environ.get("RUMI_SANDBOX_IMMUTABLE_ROOT")
    if not str(raw or "").strip():
        raise RuntimeError("SANDBOX_RUNTIME_UNAVAILABLE: immutable sandbox root is not configured")
    root = _required_dir(raw, "immutable_root")
    if root == Path("/").resolve():
        raise RuntimeError("SANDBOX_RUNTIME_UNAVAILABLE: host root cannot be used as sandbox root")
    marker = root / SANDBOX_ROOT_MARKER
    if not marker.is_file():
        raise RuntimeError("SANDBOX_RUNTIME_UNAVAILABLE: immutable sandbox root marker is missing")
    root_mode = root.stat().st_mode
    if root_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("SANDBOX_RUNTIME_UNAVAILABLE: immutable sandbox root is writable by group/other")
    mode = marker.stat().st_mode
    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("SANDBOX_RUNTIME_UNAVAILABLE: immutable sandbox root marker is writable by group/other")
    return root


def _stage_regular_tree(source_root: Path, target_root: Path) -> dict[str, int]:
    source_root = source_root.resolve()
    file_count = 0
    total_bytes = 0
    for current, dirs, files in os.walk(source_root, topdown=True, followlinks=False):
        current_path = Path(current)
        rel_dir = current_path.relative_to(source_root)
        if "__pycache__" in rel_dir.parts:
            dirs[:] = []
            continue
        target_dir = target_root / rel_dir
        target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        for dir_name in dirs:
            dir_path = current_path / dir_name
            _reject_special_or_link(dir_path, source_root)
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        for file_name in files:
            source = current_path / file_name
            _reject_special_or_link(source, source_root)
            if file_name.endswith(".pyc"):
                continue
            try:
                source.relative_to(source_root)
            except ValueError as exc:
                raise ValueError("Sandbox function staging path escapes function directory") from exc
            target = target_dir / file_name
            src, stat_result = _open_regular_source_for_stage(source)
            size = int(stat_result.st_size)
            try:
                if size > MAX_STAGE_FILE_BYTES:
                    raise ValueError("Sandbox function staging file is too large")
                file_count += 1
                total_bytes += size
                if file_count > MAX_STAGE_FILES:
                    raise ValueError("Sandbox function staging has too many files")
                if total_bytes > MAX_STAGE_TOTAL_BYTES:
                    raise ValueError("Sandbox function staging tree is too large")
                with src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
            except Exception:
                src.close()
                raise
            os.chmod(target, stat_result.st_mode & 0o700)
    return {"files": file_count, "bytes": total_bytes}


def _open_regular_source_for_stage(source: Path):
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(source, flags)
    except OSError as exc:
        raise ValueError("Sandbox function staging could not open path") from exc
    try:
        stat_result = os.fstat(fd)
        if not stat.S_ISREG(stat_result.st_mode):
            raise ValueError("Sandbox function staging only accepts regular files")
        if stat_result.st_nlink > 1:
            raise ValueError("Sandbox function staging rejects hardlinked files")
        return os.fdopen(fd, "rb"), stat_result
    except Exception:
        os.close(fd)
        raise


def _reject_special_or_link(path: Path, source_root: Path) -> None:
    try:
        lstat_result = path.lstat()
    except OSError as exc:
        raise ValueError("Sandbox function staging could not inspect path") from exc
    if stat.S_ISLNK(lstat_result.st_mode):
        raise ValueError("Sandbox function staging rejects symlinks")
    if stat.S_ISFIFO(lstat_result.st_mode) or stat.S_ISSOCK(lstat_result.st_mode):
        raise ValueError("Sandbox function staging rejects special files")
    if stat.S_ISCHR(lstat_result.st_mode) or stat.S_ISBLK(lstat_result.st_mode):
        raise ValueError("Sandbox function staging rejects device files")
    try:
        path.resolve(strict=False).relative_to(source_root)
    except ValueError as exc:
        raise ValueError("Sandbox function staging path escapes function directory") from exc


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
