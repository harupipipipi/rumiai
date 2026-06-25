from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from .errors import INVALID_PROVIDER_ID, INVALID_SANDBOX_POLICY, SandboxContractError


CANONICAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
SECRET_ENV_RE = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE|KEY|CREDENTIAL)", re.IGNORECASE)
MAX_ARGV_ITEMS = 256
MAX_ARG_LENGTH = 4096
MAX_ENV_ITEMS = 64
MAX_STDIN_CHARS = 1_000_000
MAX_TIMEOUT_MS = 600_000


def require_canonical_id(value: Any, *, field: str, code: str = INVALID_SANDBOX_POLICY) -> str:
    if not isinstance(value, str):
        raise SandboxContractError(code, f"{field} must be a canonical string id", details={"field": field})
    candidate = value.strip()
    if not CANONICAL_ID_RE.fullmatch(candidate):
        raise SandboxContractError(code, f"{field} must be a canonical string id", details={"field": field})
    return candidate


def require_provider_id(value: Any, *, field: str = "provider_id") -> str:
    return require_canonical_id(value, field=field, code=INVALID_PROVIDER_ID)


def validate_workspace_relative_path(value: Any, *, field: str = "path", default: str = ".") -> str:
    candidate = str(value if value is not None else default).strip() or default
    if "\x00" in candidate or "\\" in candidate or candidate.startswith("~"):
        raise SandboxContractError(INVALID_SANDBOX_POLICY, f"{field} must be workspace-relative")
    posix = PurePosixPath(candidate)
    windows = PureWindowsPath(candidate)
    if posix.is_absolute() or windows.is_absolute() or ".." in posix.parts:
        raise SandboxContractError(INVALID_SANDBOX_POLICY, f"{field} must not escape workspace")
    return "." if candidate == "." else posix.as_posix().rstrip("/")


def validate_exec_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise SandboxContractError(INVALID_SANDBOX_POLICY, "exec payload must be an object")
    if "command" in payload:
        raise SandboxContractError(
            INVALID_SANDBOX_POLICY,
            "sandbox exec uses argv only; raw command strings are rejected",
            details={"field": "command"},
        )
    argv_value = payload.get("argv")
    if isinstance(argv_value, str) or not isinstance(argv_value, (list, tuple)) or not argv_value:
        raise SandboxContractError(INVALID_SANDBOX_POLICY, "argv must be a non-empty array")
    if len(argv_value) > MAX_ARGV_ITEMS:
        raise SandboxContractError(INVALID_SANDBOX_POLICY, "argv has too many items")
    argv: list[str] = []
    for index, item in enumerate(argv_value):
        text = str(item or "")
        if not text or "\x00" in text or len(text) > MAX_ARG_LENGTH:
            raise SandboxContractError(
                INVALID_SANDBOX_POLICY,
                "argv items must be bounded strings",
                details={"field": f"argv[{index}]"},
            )
        argv.append(text)
    env_value = payload.get("env") or {}
    if not isinstance(env_value, Mapping) or len(env_value) > MAX_ENV_ITEMS:
        raise SandboxContractError(INVALID_SANDBOX_POLICY, "env must be a bounded object")
    env: dict[str, str] = {}
    for key, value in env_value.items():
        key_text = str(key or "")
        if not ENV_KEY_RE.fullmatch(key_text) or SECRET_ENV_RE.search(key_text):
            raise SandboxContractError(INVALID_SANDBOX_POLICY, "ambient secret-like env is not allowed")
        value_text = str(value or "")
        if "\x00" in value_text:
            raise SandboxContractError(INVALID_SANDBOX_POLICY, "env values must not contain NUL bytes")
        env[key_text] = value_text
    timeout_ms = int(payload.get("timeout_ms") or 60_000)
    if timeout_ms < 1 or timeout_ms > MAX_TIMEOUT_MS:
        raise SandboxContractError(INVALID_SANDBOX_POLICY, "timeout_ms is outside allowed range")
    stdin = payload.get("stdin")
    if stdin is not None and (not isinstance(stdin, str) or "\x00" in stdin or len(stdin) > MAX_STDIN_CHARS):
        raise SandboxContractError(INVALID_SANDBOX_POLICY, "stdin must be a bounded string")
    return {
        "argv": tuple(argv),
        "cwd": validate_workspace_relative_path(payload.get("cwd", "."), field="cwd"),
        "env": env,
        "timeout_ms": timeout_ms,
        "stdin": stdin,
    }
