from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_KIRO_COMMAND = "kiro-cli"
DEFAULT_TIMEOUT_SECONDS = 12
_ALLOWED_EFFORT_VALUES = {"low", "medium", "high", "xhigh", "max"}


class KiroCliError(RuntimeError):
    """Raised when a safe Kiro CLI probe cannot be completed."""


@dataclass(frozen=True)
class KiroCommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def resolve_kiro_command(command: str = DEFAULT_KIRO_COMMAND) -> str:
    candidate = str(command or DEFAULT_KIRO_COMMAND).strip()
    if not candidate:
        candidate = DEFAULT_KIRO_COMMAND
    expanded = str(Path(candidate).expanduser())
    if Path(expanded).is_file():
        return expanded
    resolved = shutil.which(candidate)
    return str(resolved or "")


def _secret_values(env: dict[str, str] | None = None) -> list[str]:
    combined = dict(os.environ)
    if isinstance(env, dict):
        combined.update({str(key): str(value) for key, value in env.items()})
    values: list[str] = []
    for key, value in combined.items():
        upper = key.upper()
        if not value or not any(token in upper for token in ("TOKEN", "SECRET", "PASSWORD", "API_KEY")):
            continue
        values.append(value)
    return sorted(set(values), key=len, reverse=True)


def _redact(text: str, *, env: dict[str, str] | None = None) -> str:
    output = str(text or "")
    for secret in _secret_values(env):
        output = output.replace(secret, "[REDACTED]")
    return output


def run_kiro_command(
    args: Iterable[str],
    *,
    command: str = DEFAULT_KIRO_COMMAND,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> KiroCommandResult:
    executable = resolve_kiro_command(command)
    if not executable:
        raise KiroCliError("kiro-cli is not installed or not available on PATH")

    argv = [executable, *[str(item) for item in args]]
    process_env = os.environ.copy()
    if isinstance(env, dict):
        process_env.update({str(key): str(value) for key, value in env.items()})
    try:
        completed = subprocess.run(
            argv,
            cwd=str(Path(cwd).expanduser().resolve()) if cwd else None,
            env=process_env,
            text=True,
            capture_output=True,
            timeout=max(1, int(timeout_seconds)),
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise KiroCliError(f"kiro-cli timed out after {max(1, int(timeout_seconds))} seconds") from exc
    except OSError as exc:
        raise KiroCliError(f"failed to start kiro-cli: {exc}") from exc

    return KiroCommandResult(
        args=tuple(argv),
        returncode=int(completed.returncode),
        stdout=_redact(completed.stdout, env=env),
        stderr=_redact(completed.stderr, env=env),
    )


def _parse_json_output(text: str) -> Any:
    raw = str(text or "").strip()
    if not raw:
        raise KiroCliError("kiro-cli returned empty JSON output")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for index in range(len(lines)):
        candidate = "\n".join(lines[index:])
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise KiroCliError("kiro-cli returned malformed JSON output")


def _model_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return list(payload)
    if not isinstance(payload, dict):
        return []
    for key in ("models", "data", "items", "available_models", "availableModels"):
        value = payload.get(key)
        if isinstance(value, list):
            return list(value)
    result = payload.get("result")
    if isinstance(result, dict):
        return _model_items(result)
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = list(value)
    else:
        candidates = []
    output: list[str] = []
    for candidate in candidates:
        item = str(candidate or "").strip().lower()
        if item and item not in output:
            output.append(item)
    return output


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_kiro_models(payload: Any, *, connection_id: str = "default") -> list[dict[str, Any]]:
    """Normalize `kiro-cli chat --list-models --format json` output.

    The CLI output shape can evolve, so this parser accepts both a top-level list
    and common wrapped-list shapes while preserving the exact advertised model ID.
    """

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    connection = str(connection_id or "default").strip() or "default"

    for raw in _model_items(payload):
        if isinstance(raw, str):
            model_id = raw.strip()
            item: dict[str, Any] = {"id": model_id, "display_name": model_id}
        elif isinstance(raw, dict):
            item = dict(raw)
            model_id = _first_text(
                item,
                "id",
                "model_id",
                "modelId",
                "value",
                "selector",
                "name",
            )
        else:
            continue
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)

        display_name = _first_text(item, "display_name", "displayName", "label", "name") or model_id
        lifecycle = _first_text(item, "lifecycle", "status", "stage").lower() or "unknown"
        effort_values = _string_list(
            item.get("effort_values")
            or item.get("effortValues")
            or item.get("reasoning_efforts")
            or item.get("reasoningEfforts")
            or item.get("effort_levels")
            or item.get("effortLevels")
        )
        effort_values = [value for value in effort_values if value in _ALLOWED_EFFORT_VALUES]

        context_window = item.get("context_window")
        if context_window is None:
            context_window = item.get("contextWindow")
        try:
            context_window_value = int(context_window or 0)
        except (TypeError, ValueError):
            context_window_value = 0

        normalized.append(
            {
                "coding_backend_id": "kiro-cli",
                "connection_id": connection,
                "agent_model_id": model_id,
                "qualified_agent_model_id": f"acp/kiro-cli/{connection}/{model_id}",
                "display_name": display_name,
                "lifecycle": lifecycle,
                "context_window": context_window_value,
                "effort_values": effort_values,
                "region": _first_text(item, "region"),
                "source": "kiro_cli_list_models",
                "raw": item,
            }
        )
    return normalized


def list_kiro_models(
    *,
    command: str = DEFAULT_KIRO_COMMAND,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    connection_id: str = "default",
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    result = run_kiro_command(
        ["chat", "--list-models", "--format", "json"],
        command=command,
        timeout_seconds=timeout_seconds,
        env=env,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise KiroCliError(f"failed to list Kiro models: {detail}")
    return normalize_kiro_models(_parse_json_output(result.stdout), connection_id=connection_id)


def _safe_account(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    source = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload
    safe: dict[str, Any] = {}
    for source_key, target_key in (
        ("email", "email"),
        ("username", "username"),
        ("user", "username"),
        ("auth_method", "auth_method"),
        ("authMethod", "auth_method"),
        ("license", "license"),
        ("plan", "plan"),
        ("region", "region"),
    ):
        value = source.get(source_key)
        if value not in (None, "") and target_key not in safe:
            safe[target_key] = str(value)
    return safe


def kiro_cli_status(
    *,
    command: str = DEFAULT_KIRO_COMMAND,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    include_models: bool = True,
    connection_id: str = "default",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    executable = resolve_kiro_command(command)
    if not executable:
        return {
            "supported": True,
            "provider_id": "kiro-cli",
            "provider_kind": "coding_backend",
            "installed": False,
            "connected": False,
            "status": "missing_cli",
            "models": [],
        }

    version_result = run_kiro_command(
        ["--version"], command=executable, timeout_seconds=timeout_seconds, env=env
    )
    version_text = version_result.stdout.strip() or version_result.stderr.strip()
    version = version_text.splitlines()[0] if version_text else ""

    whoami_result = run_kiro_command(
        ["whoami", "--format", "json"],
        command=executable,
        timeout_seconds=timeout_seconds,
        env=env,
    )
    account: dict[str, Any] = {}
    connected = whoami_result.returncode == 0
    if connected:
        try:
            account = _safe_account(_parse_json_output(whoami_result.stdout))
        except KiroCliError:
            account = {}

    status = "connected" if connected else "login_required"
    models: list[dict[str, Any]] = []
    model_error = ""
    if connected and include_models:
        try:
            models = list_kiro_models(
                command=executable,
                timeout_seconds=timeout_seconds,
                connection_id=connection_id,
                env=env,
            )
        except KiroCliError as exc:
            model_error = str(exc)
            status = "connected_model_list_error"

    return {
        "supported": True,
        "provider_id": "kiro-cli",
        "provider_kind": "coding_backend",
        "installed": True,
        "command": executable,
        "version": version,
        "connected": connected,
        "status": status,
        "account": account,
        "model_count": len(models),
        "models": models,
        "model_error": model_error,
        "auth_hint": "Run `kiro-cli login` or configure KIRO_API_KEY for explicit headless automation.",
    }


def build_kiro_headless_command(
    prompt: str,
    *,
    command: str = DEFAULT_KIRO_COMMAND,
    trusted_tools: Iterable[str] | None = None,
    effort: str = "",
    agent: str = "",
) -> list[str]:
    """Build, but do not execute, a least-privilege Kiro headless command."""

    text = str(prompt or "").strip()
    if not text:
        raise ValueError("prompt is required")
    executable = resolve_kiro_command(command) or str(command or DEFAULT_KIRO_COMMAND).strip()
    argv = [executable, "chat", "--no-interactive"]

    tools: list[str] = []
    for value in trusted_tools or []:
        item = str(value or "").strip()
        if item and item not in tools:
            tools.append(item)
    if tools:
        argv.append("--trust-tools=" + ",".join(tools))

    normalized_effort = str(effort or "").strip().lower()
    if normalized_effort:
        if normalized_effort not in _ALLOWED_EFFORT_VALUES:
            raise ValueError(f"unsupported Kiro effort value: {normalized_effort}")
        argv.extend(["--effort", normalized_effort])

    agent_name = str(agent or "").strip()
    if agent_name:
        argv.extend(["--agent", agent_name])
    argv.append(text)
    return argv
