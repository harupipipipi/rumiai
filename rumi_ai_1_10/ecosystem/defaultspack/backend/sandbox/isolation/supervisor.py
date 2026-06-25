from __future__ import annotations

import io
import json
import os
import platform
import shutil
import shlex
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Any

from ..errors import (
    SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE,
    SANDBOX_RUNTIME_UNAVAILABLE,
)
from ..policy import validate_workspace_relative_path
from .bubblewrap_builder import build_bubblewrap_argv
from .cgroup import build_systemd_run_argv, probe_systemd_user_scope
from .spec import BubblewrapSandboxSpec, CgroupLimits, WorkspaceMount


MAX_SANDBOX_OUTPUT_BYTES = 1024 * 1024
MAX_SANDBOX_TERMINAL_OUTPUT_BYTES = 256 * 1024
MAX_STAGE_FILES = 1024
MAX_STAGE_TOTAL_BYTES = 16 * 1024 * 1024
MAX_STAGE_FILE_BYTES = 2 * 1024 * 1024
MAX_CODING_WORKSPACE_EXPORT_BYTES = 128 * 1024 * 1024
MAX_CODING_WORKSPACE_EXPORT_FILES = 8000
MAX_CODING_WORKSPACE_EXPORT_FILE_BYTES = 4 * 1024 * 1024
SANDBOX_ROOT_MARKER = ".rumi-sandbox-root"
LIMA_NETWORK_ATTEST_ENV = "RUMI_SANDBOX_LIMA_NETWORK_ISOLATED"


class ManagedSandboxSupervisor:
    """Execute untrusted functions inside Bubblewrap plus a systemd cgroup."""

    def __init__(self, provider_registry: Any | None = None) -> None:
        self.provider_registry = provider_registry

    def available(self) -> bool:
        return bool(diagnose_sandbox_environment()["ready"])

    def execute_capability(self, request: dict[str, Any]) -> dict[str, Any]:
        diagnostics = diagnose_sandbox_environment(request)
        if not diagnostics["ready"]:
            failed = _first_failed_sandbox_check(diagnostics)
            message = str(failed.get("message") or "Managed sandbox runtime is unavailable")
            code = str(failed.get("code") or SANDBOX_RUNTIME_UNAVAILABLE)
            if code == SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE:
                return self._unavailable(
                    request,
                    message,
                    error_type=SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE,
                    diagnostics=diagnostics,
                )
            return self._unavailable(
                request,
                message,
                error_type=SANDBOX_RUNTIME_UNAVAILABLE,
                diagnostics=diagnostics,
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

    def execute_coding_terminal(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run a coding command inside an isolated staged workspace."""
        system = platform.system().lower()
        if system == "darwin":
            return self._execute_coding_terminal_lima(request)
        return self._execute_coding_terminal_bwrap(request)

    def _execute_coding_terminal_bwrap(self, request: dict[str, Any]) -> dict[str, Any]:
        diagnostics = diagnose_sandbox_environment(request)
        if not diagnostics["ready"]:
            failed = _first_failed_sandbox_check(diagnostics)
            return self._unavailable(
                request,
                str(failed.get("message") or "Managed sandbox runtime is unavailable"),
                error_type=str(failed.get("code") or SANDBOX_RUNTIME_UNAVAILABLE),
                diagnostics=diagnostics,
            )
        timeout = _bounded_timeout(request.get("timeout_seconds"))
        sandbox_id = _sandbox_id(request)
        workspace = _required_dir(request.get("workspace_root"), "workspace_root")
        cwd = validate_workspace_relative_path(request.get("cwd", "."), field="cwd")
        command_argv = _coding_command_argv(request)
        try:
            immutable_root = _immutable_root(request)
            spec = BubblewrapSandboxSpec(
                sandbox_id=sandbox_id,
                profile_id=str(request.get("profile_runtime") or request.get("principal_id") or "coding"),
                immutable_root=immutable_root,
                workspace=WorkspaceMount(source=workspace, read_only=False),
                argv=tuple(command_argv),
                env=_coding_sandbox_env(sandbox_id),
                network_enabled=bool(request.get("network_enabled") is True),
            )
            bwrap_argv = build_bubblewrap_argv(spec)
            if cwd != ".":
                marker = bwrap_argv.index("--chdir")
                bwrap_argv[marker + 1] = "/workspace/" + cwd
            with tempfile.TemporaryDirectory(prefix=f"{sandbox_id}-term-") as tmp:
                temp_root = Path(tmp)
                sandbox_command, stdout_path, stderr_path, returncode_path = _sandbox_wrapper_command(
                    temp_root=temp_root,
                    bwrap_argv=bwrap_argv,
                    seccomp_profile=None,
                )
                command = build_systemd_run_argv(
                    f"rumi-sandbox-terminal-{sandbox_id}",
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
            return _coding_terminal_response(
                sandbox_id=sandbox_id,
                command=request.get("command") or request.get("argv"),
                returncode=None,
                stdout="",
                stderr="Managed sandbox terminal timed out",
                timed_out=True,
            )
        except Exception as exc:
            return self._unavailable(
                request,
                str(exc),
                error_type=SANDBOX_RUNTIME_UNAVAILABLE,
            )
        return _coding_terminal_response(
            sandbox_id=sandbox_id,
            command=request.get("command") or request.get("argv"),
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            timed_out=False,
        )

    def _execute_coding_terminal_lima(self, request: dict[str, Any]) -> dict[str, Any]:
        limactl = shutil.which("limactl")
        instance = str(os.environ.get("RUMI_SANDBOX_LIMA_INSTANCE") or "").strip()
        if limactl is None:
            return self._unavailable(
                request,
                "Lima sandbox runtime is not installed",
                error_type=SANDBOX_RUNTIME_UNAVAILABLE,
            )
        if not instance:
            return self._unavailable(
                request,
                "Lima sandbox instance is not configured; set RUMI_SANDBOX_LIMA_INSTANCE",
                error_type=SANDBOX_RUNTIME_UNAVAILABLE,
            )
        if str(os.environ.get(LIMA_NETWORK_ATTEST_ENV) or "").strip().lower() not in {"1", "true", "yes", "on"}:
            return self._unavailable(
                request,
                "Lima sandbox network isolation is not attested; set RUMI_SANDBOX_LIMA_NETWORK_ISOLATED=true for a networkless VM",
                error_type=SANDBOX_RUNTIME_UNAVAILABLE,
            )
        sandbox_id = _sandbox_id(request)
        timeout = _bounded_timeout(request.get("timeout_seconds"))
        workspace = _required_dir(request.get("workspace_root"), "workspace_root")
        cwd = validate_workspace_relative_path(request.get("cwd", "."), field="cwd")
        remote_root = f"/tmp/rumi-sandbox-coding/{sandbox_id}"
        try:
            archive = _tar_directory(workspace)
            import_script = f"rm -rf {shlex.quote(remote_root)} && mkdir -p {shlex.quote(remote_root)} && tar -xf - -C {shlex.quote(remote_root)}"
            import_proc = subprocess.run(
                [limactl, "shell", instance, "--", "sh", "-lc", import_script],
                input=archive,
                capture_output=True,
                timeout=timeout + 2,
                close_fds=True,
            )
            if import_proc.returncode != 0:
                return _coding_terminal_response(
                    sandbox_id=sandbox_id,
                    command=request.get("command") or request.get("argv"),
                    returncode=import_proc.returncode,
                    stdout="",
                    stderr=_decode_bytes(import_proc.stderr),
                    timed_out=False,
                    success=False,
                )
            remote_cwd = remote_root if cwd == "." else remote_root.rstrip("/") + "/" + cwd
            exec_script = (
                f"cd {shlex.quote(remote_cwd)} && "
                f"HOME=/tmp PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
                f"RUMI_SANDBOX_ID={shlex.quote(sandbox_id)} "
                + _remote_shell_command(request)
            )
            proc = subprocess.run(
                [limactl, "shell", instance, "--", "sh", "-lc", exec_script],
                capture_output=True,
                timeout=timeout + 2,
                close_fds=True,
            )
            with tempfile.TemporaryDirectory(prefix=f"{sandbox_id}-lima-export-") as export_tmp:
                export_path = Path(export_tmp) / "workspace.tar"
                with export_path.open("wb") as export_handle:
                    export_proc = subprocess.run(
                        [limactl, "shell", instance, "--", "tar", "-cf", "-", "-C", remote_root, "."],
                        stdout=export_handle,
                        stderr=subprocess.PIPE,
                        timeout=timeout + 2,
                        close_fds=True,
                    )
                if export_proc.returncode == 0:
                    if export_path.stat().st_size > MAX_CODING_WORKSPACE_EXPORT_BYTES:
                        return _coding_terminal_response(
                            sandbox_id=sandbox_id,
                            command=request.get("command") or request.get("argv"),
                            returncode=1,
                            stdout=_decode_bytes(proc.stdout),
                            stderr="Lima sandbox export exceeded workspace size quota",
                            timed_out=False,
                            success=False,
                            provider_id="lima_ubuntu",
                        )
                    _replace_directory_from_tar(workspace, export_path)
        except subprocess.TimeoutExpired:
            return _coding_terminal_response(
                sandbox_id=sandbox_id,
                command=request.get("command") or request.get("argv"),
                returncode=None,
                stdout="",
                stderr="Lima sandbox terminal timed out",
                timed_out=True,
            )
        except Exception as exc:
            return self._unavailable(request, str(exc), error_type=SANDBOX_RUNTIME_UNAVAILABLE)
        return _coding_terminal_response(
            sandbox_id=sandbox_id,
            command=request.get("command") or request.get("argv"),
            returncode=proc.returncode,
            stdout=_decode_bytes(proc.stdout),
            stderr=_decode_bytes(proc.stderr),
            timed_out=False,
            provider_id="lima_ubuntu",
        )

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
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
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
        if diagnostics is not None:
            payload["diagnostics"] = diagnostics
        return payload


def diagnose_sandbox_environment(request: dict[str, Any] | None = None) -> dict[str, Any]:
    request = request if isinstance(request, dict) else {}
    checks: list[dict[str, Any]] = []

    bwrap_path = shutil.which("bwrap")
    checks.append(
        {
            "name": "bubblewrap",
            "ok": bwrap_path is not None,
            "path": bwrap_path,
            "code": SANDBOX_RUNTIME_UNAVAILABLE,
            "message": (
                "Bubblewrap sandbox runtime is available"
                if bwrap_path is not None
                else "Bubblewrap sandbox runtime is not installed"
            ),
        }
    )

    systemd_probe = probe_systemd_user_scope()
    systemd_check: dict[str, Any] = {
        "name": "systemd_user_scope",
        "ok": systemd_probe.ok,
        "path": systemd_probe.path,
        "code": SANDBOX_RESOURCE_CONTROLLER_UNAVAILABLE,
        "message": systemd_probe.message,
    }
    if systemd_probe.returncode is not None:
        systemd_check["returncode"] = systemd_probe.returncode
    if systemd_probe.stderr:
        systemd_check["stderr"] = systemd_probe.stderr
    checks.append(systemd_check)

    try:
        immutable_root = _immutable_root(request)
        checks.append(
            {
                "name": "immutable_root",
                "ok": True,
                "path": str(immutable_root),
                "marker": str(immutable_root / SANDBOX_ROOT_MARKER),
                "code": SANDBOX_RUNTIME_UNAVAILABLE,
                "message": "Immutable sandbox root is configured",
            }
        )
    except Exception as exc:
        checks.append(
            {
                "name": "immutable_root",
                "ok": False,
                "path": str(request.get("immutable_root") or os.environ.get("RUMI_SANDBOX_IMMUTABLE_ROOT") or ""),
                "marker": SANDBOX_ROOT_MARKER,
                "code": SANDBOX_RUNTIME_UNAVAILABLE,
                "message": _sandbox_root_error_message(exc),
            }
        )

    return {
        "ready": all(bool(check.get("ok")) for check in checks),
        "checks": checks,
    }


def _first_failed_sandbox_check(diagnostics: dict[str, Any]) -> dict[str, Any]:
    checks = diagnostics.get("checks") if isinstance(diagnostics, dict) else []
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict) and not bool(check.get("ok")):
                return check
    return {
        "name": "managed_sandbox",
        "ok": False,
        "code": SANDBOX_RUNTIME_UNAVAILABLE,
        "message": "Managed sandbox runtime is unavailable",
    }


def _sandbox_root_error_message(exc: Exception) -> str:
    text = str(exc)
    prefix = "SANDBOX_RUNTIME_UNAVAILABLE:"
    if text.startswith(prefix):
        text = text[len(prefix):].strip()
    if "not configured" in text:
        return (
            "Immutable sandbox root is not configured; set "
            "RUMI_SANDBOX_IMMUTABLE_ROOT or pass a server-side immutable_root"
        )
    if text:
        return f"Immutable sandbox root is invalid: {text}"
    return "Immutable sandbox root is invalid"


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


def _coding_command_argv(request: dict[str, Any]) -> list[str]:
    argv = request.get("argv")
    if isinstance(argv, list) and argv:
        return [str(item) for item in argv]
    command = str(request.get("command") or "").strip()
    if not command:
        raise ValueError("command or argv is required")
    return ["/bin/sh", "-lc", command]


def _remote_shell_command(request: dict[str, Any]) -> str:
    argv = request.get("argv")
    if isinstance(argv, list) and argv:
        return shlex.join(str(item) for item in argv)
    command = str(request.get("command") or "").strip()
    if not command:
        raise ValueError("command or argv is required")
    return "/bin/sh -lc " + shlex.quote(command)


def _coding_sandbox_env(sandbox_id: str) -> dict[str, str]:
    return {
        "HOME": "/home",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "RUMI_SANDBOX_ID": sandbox_id,
    }


def _coding_terminal_response(
    *,
    sandbox_id: str,
    command: Any,
    returncode: int | None,
    stdout: str,
    stderr: str,
    timed_out: bool,
    success: bool | None = None,
    provider_id: str = "bwrap_host",
) -> dict[str, Any]:
    clipped_stdout, stdout_truncated = _clip_output(stdout)
    clipped_stderr, stderr_truncated = _clip_output(stderr)
    ok = returncode == 0 and not timed_out if success is None else bool(success)
    return {
        "success": ok,
        "ok": ok,
        "sandbox_id": sandbox_id,
        "execution_boundary": "managed_sandbox",
        "provider_id": provider_id,
        "command": command,
        "exit_code": returncode,
        "returncode": returncode,
        "stdout": clipped_stdout,
        "stderr": clipped_stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "timed_out": timed_out,
        "process_failed": returncode not in (0, None),
    }


def _clip_output(text: Any) -> tuple[str, bool]:
    value = str(text or "")
    raw = value.encode("utf-8", errors="replace")
    if len(raw) <= MAX_SANDBOX_TERMINAL_OUTPUT_BYTES:
        return value, False
    clipped = raw[:MAX_SANDBOX_TERMINAL_OUTPUT_BYTES].decode("utf-8", errors="replace")
    return clipped + "\n[output truncated]\n", True


def _decode_bytes(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _tar_directory(root: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for current, dirs, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
            for file_name in files:
                path = current_path / file_name
                if not path.is_file() or path.is_symlink():
                    continue
                archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    return buffer.getvalue()


def _replace_directory_from_tar(root: Path, archive: bytes | Path) -> None:
    with tempfile.TemporaryDirectory(prefix="rumi-sandbox-export-") as tmp:
        target = Path(tmp) / "work"
        target.mkdir(mode=0o700)
        target_root = target.resolve()
        if isinstance(archive, Path):
            tar_context = tarfile.open(archive, mode="r:*")
        else:
            tar_context = tarfile.open(fileobj=io.BytesIO(archive), mode="r:*")
        with tar_context as tar:
            file_count = 0
            total_bytes = 0
            for member in tar:
                member_path = (target / member.name).resolve()
                try:
                    member_path.relative_to(target_root)
                except ValueError as exc:
                    raise ValueError("sandbox export attempted path traversal") from exc
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    continue
                if member.isfile():
                    file_count += 1
                    total_bytes += int(member.size)
                    if file_count > MAX_CODING_WORKSPACE_EXPORT_FILES:
                        raise ValueError("sandbox export has too many files")
                    if member.size > MAX_CODING_WORKSPACE_EXPORT_FILE_BYTES:
                        raise ValueError("sandbox export contains an oversized file")
                    if total_bytes > MAX_CODING_WORKSPACE_EXPORT_BYTES:
                        raise ValueError("sandbox export is too large")
                tar.extract(member, target, filter="data")
        for item in root.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        for item in target.iterdir():
            shutil.move(str(item), str(root / item.name))


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
