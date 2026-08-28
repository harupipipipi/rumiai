"""Receipt-gated workspace-jailed bounded shell execution."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from core_runtime.bounded_process_runner import (
    HostBoundedProcessRunner,
    ProcessExecutionPolicy,
)
from ecosystem.rumi_host_authority_bridge_pack.runtime.bridge import (
    HostAuthorityScope,
    require_authenticated_host_context,
)

AUTHORITY = "rumi.service.host.authorize.v1"
POLICY = "rumi.service.shell.inspect.v1"
WORKSPACE = "rumi.resource.workspace.v1"
SERVICE_PACK_ID = "rumi_shell_execute_pack"
_MAX_OUTPUT_BYTES = 128 * 1024
_MAX_TIMEOUT = 900
_ENV_ALLOWLIST = frozenset({"LANG", "LC_ALL", "TEMP", "TMP", "TMPDIR"})
_SECRET_ENV_WORDS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "credential",
    "authorization",
    "cookie",
)
_RAW_CREDENTIAL_FIELDS = frozenset(
    {
        "access_token",
        "api_key",
        "approval_token",
        "authority_token",
        "credential",
        "credential_handle",
        "password",
        "secret",
        "token",
    }
)


class ShellExecuteService:
    """Execute one bounded command after exact Host authority redemption."""

    def __init__(
        self,
        client: Any,
        *,
        host_context: object | None = None,
    ) -> None:
        self.client = client
        self.host_context = (
            host_context
            if host_context is not None
            else getattr(client, "host_context", client)
        )
        self.runner = HostBoundedProcessRunner()

    def invoke(self, name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Execute one command; Host identity and approval are not payload data."""
        if name != "execute":
            raise ValueError(f"unknown shell execute operation: {name}")
        host_scope = self._host_scope()
        arguments = _arguments(payload)
        policy = self.client.invoke(POLICY, "classify", arguments)
        if not isinstance(policy, Mapping):
            raise PermissionError("shell policy response is invalid")
        if policy.get("shell_syntax") and not arguments["shell"]:
            raise PermissionError("shell syntax requires explicit shell mode")
        root = self._workspace(host_scope)
        cwd = _cwd(root, arguments["cwd"])
        argv = _execution_argv(arguments, cwd, root)
        environment = _host_environment(arguments["env"])
        process_policy = _process_policy(argv, cwd, environment)
        self._redeem(payload, arguments)
        started = time.monotonic()
        result = self.runner.run_local(
            argv=argv,
            cwd=cwd,
            stdin=None,
            timeout_seconds=arguments["timeout"],
            environment=environment,
            policy=process_policy,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        relative_cwd = cwd.relative_to(root).as_posix() if cwd != root else "."
        return {
            "command": arguments["command"],
            "workspace_id": host_scope.workspace_id,
            "cwd": relative_cwd,
            "classification": policy.get("classification"),
            "risk_reasons": list(policy.get("risk_reasons") or []),
            "approval_required": bool(policy.get("approval_required")),
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stdout_truncated": result.stdout_truncated,
            "stderr_truncated": result.stderr_truncated,
            "timed_out": result.timed_out,
            "duration_ms": duration_ms,
            "executed": result.transport_error is None,
            "transport_error": result.transport_error,
            "authority_receipt_redeemed": True,
            "attestation": _attestation(result.attestation),
        }

    def _host_scope(self) -> HostAuthorityScope:
        """Revalidate the Host envelope at every effect boundary."""

        return require_authenticated_host_context(self.host_context)

    def _workspace(self, host_scope: HostAuthorityScope) -> Path:
        workspace_id = host_scope.workspace_id
        if not workspace_id:
            raise PermissionError("Host workspace binding is unavailable")
        mount = self.client.invoke(
            WORKSPACE,
            "get",
            {"workspace_id": workspace_id},
        )
        if not isinstance(mount, Mapping):
            raise KeyError("workspace mount is unknown")
        root = Path(str(mount.get("root_path") or "")).resolve(strict=True)
        if not root.is_dir():
            raise PermissionError("workspace root is unavailable")
        return root

    def _redeem(
        self, payload: Mapping[str, Any], arguments: Mapping[str, Any]
    ) -> None:
        """Redeem only the opaque receipt and effect data at the boundary."""

        result = self.client.invoke(
            AUTHORITY,
            "redeem",
            {
                "receipt": str(payload.get("authority_receipt") or ""),
                "service_pack_id": SERVICE_PACK_ID,
                "operation": "shell.execute",
                "authority": "shell.execute",
                "arguments": dict(arguments),
            },
        )
        if not isinstance(result, Mapping) or not result.get("authorized"):
            reason = result.get("reason") if isinstance(result, Mapping) else None
            raise PermissionError(str(reason or "shell authority denied"))


def create_shell_execute_operation(
    client: Any,
    *,
    host_context: object | None = None,
) -> Callable[[str, Mapping[str, Any]], Any]:
    """Create receipt-gated shell execution."""

    return ShellExecuteService(client, host_context=host_context).invoke


def _arguments(payload: Mapping[str, Any]) -> dict[str, Any]:
    for field_name in _RAW_CREDENTIAL_FIELDS:
        if field_name in payload and payload.get(field_name) not in (None, ""):
            raise PermissionError(f"raw shell credential is denied: {field_name}")
    command = payload.get("command")
    if not isinstance(command, (str, list, tuple)) or not command:
        raise ValueError("command is required")
    timeout = max(1, min(_MAX_TIMEOUT, int(payload.get("timeout") or 30)))
    env = payload.get("env")
    if env is not None and not isinstance(env, Mapping):
        raise ValueError("shell environment must be an object")
    normalized_command: str | list[str]
    if isinstance(command, (list, tuple)):
        normalized_command = [str(item) for item in command]
    else:
        normalized_command = command
    return {
        "command": normalized_command,
        "cwd": str(payload.get("cwd") or "."),
        "timeout": timeout,
        "shell": bool(payload.get("shell", False)),
        "env": {str(key): str(value) for key, value in (env or {}).items()},
    }


def _cwd(root: Path, value: str) -> Path:
    raw = Path(str(value or "."))
    if raw.is_absolute():
        raise PermissionError("absolute shell cwd is denied")
    resolved = (root / raw).resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError("shell cwd escapes workspace") from exc
    if not resolved.is_dir():
        raise NotADirectoryError("shell cwd is not a directory")
    return resolved


def _argv(command: Any) -> list[str]:
    if isinstance(command, list):
        result = [str(item) for item in command]
    else:
        result = shlex.split(str(command), posix=sys.platform != "win32")
    if not result or any("\x00" in item for item in result):
        raise ValueError("command arguments are invalid")
    return result


def _execution_argv(
    arguments: Mapping[str, Any],
    cwd: Path,
    root: Path,
) -> list[str]:
    command = arguments["command"]
    if arguments["shell"]:
        if not isinstance(command, str) or "\x00" in command:
            raise ValueError("shell command must be text without NUL bytes")
        return _shell_argv(command, cwd, root)
    argv = _argv(command)
    argv[0] = _resolve_executable(argv[0], cwd, root)
    return argv


def _shell_argv(command: str, cwd: Path, root: Path) -> list[str]:
    del cwd, root
    if os.name == "nt":
        shell = Path(r"C:\Windows\System32\cmd.exe")
    else:
        shell = Path("/bin/sh")
    if not shell.is_file() or not os.access(shell, os.X_OK):
        raise PermissionError("Host shell executable is unavailable")
    return [str(shell), "/c" if os.name == "nt" else "-c", command]


def _resolve_executable(value: str, cwd: Path, root: Path) -> str:
    raw = str(value or "").strip()
    if not raw or "\x00" in raw:
        raise ValueError("process executable is invalid")
    if os.path.isabs(raw):
        candidate = Path(raw)
    elif "/" in raw or "\\" in raw:
        candidate = (cwd / raw).resolve(strict=True)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PermissionError("relative executable escapes workspace") from exc
    else:
        resolved = shutil.which(raw, path=_host_search_path())
        if resolved is None:
            raise FileNotFoundError(f"Host executable is unavailable: {raw}")
        candidate = Path(resolved).resolve(strict=True)
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise PermissionError("Host executable is unavailable")
    return str(candidate)


def _host_search_path() -> str:
    """Return a deterministic search path without reading ambient PATH."""

    executable_dir = Path(sys.executable).resolve().parent
    entries = [str(executable_dir)]
    entries.extend(item for item in os.defpath.split(os.pathsep) if item)
    return os.pathsep.join(dict.fromkeys(entries))


def _environment(overrides: Mapping[str, str]) -> dict[str, str]:
    """Build an empty-by-default environment from an explicit allowlist."""

    environment: dict[str, str] = {}
    for raw_key, value in overrides.items():
        key = str(raw_key)
        upper = key.upper()
        if _secret_key(key):
            raise PermissionError(f"secret shell environment key is denied: {key}")
        if upper == "PATH":
            raise PermissionError("shell PATH is Host-owned")
        if upper not in _ENV_ALLOWLIST:
            raise PermissionError(f"shell environment key is denied: {key}")
        if "\x00" in key or "\x00" in value:
            raise ValueError("shell environment contains a NUL byte")
        environment[upper] = str(value)
    return environment


def _host_environment(overrides: Mapping[str, str]) -> dict[str, str]:
    environment = _environment(overrides)
    environment["PATH"] = _host_search_path()
    return environment


def _secret_key(key: str) -> bool:
    lower = key.casefold()
    return any(word in lower for word in _SECRET_ENV_WORDS)


def _process_policy(
    argv: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
) -> ProcessExecutionPolicy:
    exact_argv = tuple(argv)
    return ProcessExecutionPolicy(
        allowed_executables=frozenset({exact_argv[0]}),
        allowed_argv=(exact_argv,),
        allowed_cwds=(cwd,),
        allowed_environment=frozenset(environment),
        max_stdin_bytes=1,
        max_stdout_bytes=_MAX_OUTPUT_BYTES,
        max_stderr_bytes=_MAX_OUTPUT_BYTES,
        max_timeout_seconds=_MAX_TIMEOUT,
        allow_path_search=False,
    )


def _attestation(value: Any) -> dict[str, Any]:
    return {
        "authority": str(getattr(value, "authority", "")),
        "boundary": str(getattr(value, "boundary", "")),
        "sandboxed": bool(getattr(value, "sandboxed", False)),
        "process_tree_kill": str(getattr(value, "process_tree_kill", "")),
    }
