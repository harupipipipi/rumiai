"""Host-owned, fail-closed process execution boundary."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)((?:api[_-]?key|password|secret|token)[\"']?\s*[:=]\s*[\"']?)"
    r"([^\"'\s,}]+)"
)
_MAX_ARGV_ITEMS = 256
_MAX_ARG_BYTES = 64 * 1024


@dataclass(frozen=True)
class ProcessExecutionPolicy:
    """Exact Host policy for one bounded process request."""

    allowed_executables: frozenset[str]
    allowed_argv: tuple[tuple[str, ...], ...]
    allowed_cwds: tuple[Path, ...]
    allowed_environment: frozenset[str] = frozenset()
    max_stdin_bytes: int = 1024 * 1024
    max_stdout_bytes: int = 256 * 1024
    max_stderr_bytes: int = 64 * 1024
    max_timeout_seconds: float = 300.0
    redact_values: tuple[str, ...] = ()
    allow_path_search: bool = False


@dataclass(frozen=True)
class HostProcessAttestation:
    """Host measurement of the boundary that actually executed the process."""

    authority: str
    boundary: str
    sandboxed: bool
    process_tree_kill: str


@dataclass(frozen=True)
class BoundedProcessResult:
    """Bounded, redacted result. Raw process material is never persisted here."""

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool
    attestation: HostProcessAttestation
    transport_error: str | None = None

    @property
    def completed(self) -> bool:
        return self.exit_code is not None


@dataclass
class _CappedBytes:
    limit: int
    data: bytearray = field(default_factory=bytearray)
    truncated: bool = False

    def append(self, chunk: bytes) -> None:
        remaining = max(0, self.limit - len(self.data))
        self.data.extend(chunk[:remaining])
        if len(chunk) > remaining:
            self.truncated = True


class HostBoundedProcessRunner:
    """Validate, execute, cap, redact, and attest Host process requests."""

    AUTHORITY = "core_runtime.bounded_process_runner"

    def run_local(
        self,
        *,
        argv: Sequence[str],
        cwd: Path,
        stdin: str | None,
        timeout_seconds: float,
        environment: Mapping[str, str],
        policy: ProcessExecutionPolicy,
    ) -> BoundedProcessResult:
        request = self._validate_request(
            argv=argv,
            cwd=cwd,
            stdin=stdin,
            timeout_seconds=timeout_seconds,
            environment=environment,
            policy=policy,
        )
        stdout_buffer = _CappedBytes(policy.max_stdout_bytes)
        stderr_buffer = _CappedBytes(policy.max_stderr_bytes)
        popen_kwargs: dict[str, Any] = {
            "args": request["argv"],
            "cwd": request["cwd"],
            "env": request["environment"],
            "stdin": subprocess.PIPE if request["stdin"] is not None else subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "close_fds": True,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        elif os.name == "nt":
            popen_kwargs["creationflags"] = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0x00000200,
            )
        process = subprocess.Popen(**popen_kwargs)
        io_threads = [
            threading.Thread(
                target=self._drain,
                args=(process.stdout, stdout_buffer),
                daemon=True,
            ),
            threading.Thread(
                target=self._drain,
                args=(process.stderr, stderr_buffer),
                daemon=True,
            ),
        ]
        if request["stdin"] is not None and process.stdin is not None:
            io_threads.append(
                threading.Thread(
                    target=self._write_stdin,
                    args=(process.stdin, request["stdin"]),
                    daemon=True,
                )
            )
        for io_thread in io_threads:
            io_thread.start()
        timed_out = False
        try:
            process.wait(timeout=request["timeout_seconds"])
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate_process_tree(process)
            process.wait()
        for io_thread in io_threads:
            io_thread.join()
        attestation = HostProcessAttestation(
            authority=self.AUTHORITY,
            boundary="bounded_host_process",
            sandboxed=False,
            process_tree_kill=(
                "posix_process_group" if os.name == "posix" else "windows_process_tree"
            ),
        )
        return self._result(
            exit_code=process.returncode,
            stdout=bytes(stdout_buffer.data),
            stderr=bytes(stderr_buffer.data),
            timed_out=timed_out,
            stdout_truncated=stdout_buffer.truncated,
            stderr_truncated=stderr_buffer.truncated,
            attestation=attestation,
            transport_error=None,
            policy=policy,
        )

    def run_attested_backend(
        self,
        *,
        argv: Sequence[str],
        cwd: Path,
        stdin: str | None,
        timeout_seconds: float,
        environment: Mapping[str, str],
        policy: ProcessExecutionPolicy,
        backend: Callable[[], Mapping[str, Any]],
        boundary: str,
        sandboxed: bool,
        process_tree_kill: str,
    ) -> BoundedProcessResult:
        """Apply the same policy to a Host-owned sandbox transport."""
        self._validate_request(
            argv=argv,
            cwd=cwd,
            stdin=stdin,
            timeout_seconds=timeout_seconds,
            environment=environment,
            policy=policy,
        )
        try:
            payload = backend()
        except Exception as exc:
            error_bytes, error_truncated = self._bounded_bytes(
                str(exc).encode("utf-8", errors="replace"),
                policy.max_stderr_bytes,
            )
            return self._result(
                exit_code=None,
                stdout=b"",
                stderr=error_bytes,
                timed_out=False,
                stdout_truncated=False,
                stderr_truncated=error_truncated,
                attestation=HostProcessAttestation(
                    authority=self.AUTHORITY,
                    boundary=boundary,
                    sandboxed=sandboxed,
                    process_tree_kill=process_tree_kill,
                ),
                transport_error="provider_unavailable",
                policy=policy,
            )
        self._validate_backend_result(payload)
        stdout, stdout_truncated = self._bounded_bytes(
            str(payload["stdout"]).encode("utf-8"),
            policy.max_stdout_bytes,
        )
        stderr, stderr_truncated = self._bounded_bytes(
            str(payload["stderr"]).encode("utf-8"),
            policy.max_stderr_bytes,
        )
        exit_code = payload["exit_code"]
        timed_out = bool(payload.get("timed_out"))
        transport_error = None
        if exit_code is None:
            transport_error = str(
                payload.get("error_type") or payload.get("error") or "provider_unavailable"
            )
        return self._result(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            attestation=HostProcessAttestation(
                authority=self.AUTHORITY,
                boundary=boundary,
                sandboxed=sandboxed,
                process_tree_kill=process_tree_kill,
            ),
            transport_error=transport_error,
            policy=policy,
        )

    @staticmethod
    def _validate_request(
        *,
        argv: Sequence[str],
        cwd: Path,
        stdin: str | None,
        timeout_seconds: float,
        environment: Mapping[str, str],
        policy: ProcessExecutionPolicy,
    ) -> dict[str, Any]:
        limits = (
            policy.max_stdin_bytes,
            policy.max_stdout_bytes,
            policy.max_stderr_bytes,
        )
        if (
            any(
                isinstance(limit, bool)
                or not isinstance(limit, int)
                or limit <= 0
                or limit > 64 * 1024 * 1024
                for limit in limits
            )
            or isinstance(policy.max_timeout_seconds, bool)
            or not isinstance(policy.max_timeout_seconds, (int, float))
            or policy.max_timeout_seconds <= 0
            or policy.max_timeout_seconds > 3600
        ):
            raise ValueError("process policy violates the bounded schema")
        if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
            raise ValueError("process argv must be a sequence of strings")
        normalized_argv = tuple(argv)
        if (
            not normalized_argv
            or len(normalized_argv) > _MAX_ARGV_ITEMS
            or any(
                not isinstance(item, str) or not item or "\x00" in item
                for item in normalized_argv
            )
            or sum(len(item.encode("utf-8")) for item in normalized_argv)
            > _MAX_ARG_BYTES
        ):
            raise ValueError("process argv violates the bounded schema")
        if normalized_argv[0] not in policy.allowed_executables:
            raise PermissionError("process executable is not allowlisted")
        if (
            not policy.allow_path_search
            and not Path(normalized_argv[0]).is_absolute()
        ):
            raise PermissionError("process executable must be an absolute path")
        if normalized_argv not in policy.allowed_argv:
            raise PermissionError("process arguments are not exactly allowlisted")
        raw_cwd = Path(cwd)
        if not raw_cwd.is_absolute() or raw_cwd.is_symlink():
            raise PermissionError("process cwd must be an absolute non-symlink directory")
        normalized_cwd = raw_cwd.resolve()
        allowed_cwds = tuple(Path(item).resolve() for item in policy.allowed_cwds)
        if normalized_cwd not in allowed_cwds or not normalized_cwd.is_dir():
            raise PermissionError("process cwd is not exactly allowlisted")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
            or timeout_seconds > policy.max_timeout_seconds
        ):
            raise ValueError("process timeout violates the bounded schema")
        if stdin is not None and not isinstance(stdin, str):
            raise ValueError("process stdin must be text or null")
        stdin_bytes = stdin.encode("utf-8") if stdin is not None else None
        if stdin_bytes is not None and len(stdin_bytes) > policy.max_stdin_bytes:
            raise ValueError("process stdin exceeds the policy limit")
        normalized_environment: dict[str, str] = {}
        for key, value in environment.items():
            if (
                not isinstance(key, str)
                or not isinstance(value, str)
                or not key
                or "=" in key
                or "\x00" in key
                or "\x00" in value
            ):
                raise ValueError("process environment violates the bounded schema")
            if key not in policy.allowed_environment:
                raise PermissionError(f"process environment key is not allowlisted: {key}")
            normalized_environment[key] = value
        return {
            "argv": normalized_argv,
            "cwd": str(normalized_cwd),
            "stdin": stdin_bytes,
            "timeout_seconds": float(timeout_seconds),
            "environment": normalized_environment,
        }

    @staticmethod
    def _validate_backend_result(payload: Mapping[str, Any]) -> None:
        if not isinstance(payload, Mapping):
            raise ValueError("process backend output must be an object")
        if "exit_code" not in payload or "stdout" not in payload or "stderr" not in payload:
            raise ValueError("process backend output is missing required fields")
        exit_code = payload["exit_code"]
        if exit_code is not None and (
            isinstance(exit_code, bool) or not isinstance(exit_code, int)
        ):
            raise ValueError("process backend exit_code must be an integer or null")
        if not isinstance(payload["stdout"], str) or not isinstance(payload["stderr"], str):
            raise ValueError("process backend stdout and stderr must be strings")
        if "timed_out" in payload and not isinstance(payload["timed_out"], bool):
            raise ValueError("process backend timed_out must be boolean")

    @staticmethod
    def _drain(stream: Any, output: _CappedBytes) -> None:
        if stream is None:
            return
        try:
            for chunk in iter(lambda: stream.read(8192), b""):
                output.append(chunk)
        finally:
            stream.close()

    @staticmethod
    def _write_stdin(stream: Any, value: bytes) -> None:
        try:
            stream.write(value)
            stream.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            stream.close()

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            try:
                process.wait(timeout=0.5)
                return
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        if process.poll() is None:
            process.kill()

    @staticmethod
    def _bounded_bytes(value: bytes, limit: int) -> tuple[bytes, bool]:
        return value[:limit], len(value) > limit

    @classmethod
    def _result(
        cls,
        *,
        exit_code: int | None,
        stdout: bytes,
        stderr: bytes,
        timed_out: bool,
        stdout_truncated: bool,
        stderr_truncated: bool,
        attestation: HostProcessAttestation,
        transport_error: str | None,
        policy: ProcessExecutionPolicy,
    ) -> BoundedProcessResult:
        stdout_text, redacted_stdout_truncated = cls._redacted_bounded_text(
            stdout,
            policy.max_stdout_bytes,
            policy,
        )
        stderr_text, redacted_stderr_truncated = cls._redacted_bounded_text(
            stderr,
            policy.max_stderr_bytes,
            policy,
        )
        return BoundedProcessResult(
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
            timed_out=timed_out,
            stdout_truncated=stdout_truncated or redacted_stdout_truncated,
            stderr_truncated=stderr_truncated or redacted_stderr_truncated,
            attestation=attestation,
            transport_error=transport_error,
        )

    @classmethod
    def _redacted_bounded_text(
        cls,
        value: bytes,
        limit: int,
        policy: ProcessExecutionPolicy,
    ) -> tuple[str, bool]:
        redacted = cls._redact(value.decode("utf-8", errors="replace"), policy)
        encoded = redacted.encode("utf-8")
        clipped, truncated = cls._bounded_bytes(encoded, limit)
        return clipped.decode("utf-8", errors="replace"), truncated

    @staticmethod
    def _redact(value: str, policy: ProcessExecutionPolicy) -> str:
        redacted = value
        for secret in sorted(
            (item for item in policy.redact_values if item),
            key=len,
            reverse=True,
        ):
            redacted = redacted.replace(secret, "[REDACTED]")
        return _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", redacted)
