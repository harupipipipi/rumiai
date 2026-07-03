from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping
from urllib.parse import urlparse

from .errors import (
    DESKTOP_LEASE_REQUIRED,
    INVALID_DESKTOP_INPUT,
    INVALID_EXEC_REQUEST,
    INVALID_PROVIDER_ID,
    INVALID_SANDBOX_ID,
    RAW_COMMAND_REJECTED,
    RequestValidationError,
)


CANONICAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
DESKTOP_ACTIONS = frozenset({"move", "click", "double_click", "drag", "scroll", "type_text", "key"})
DESKTOP_BUTTONS = frozenset({"left", "middle", "right"})
MAX_ARGV_ITEMS = 256
MAX_ARG_LENGTH = 4096
MAX_ENV_ITEMS = 128
MAX_STDIN_CHARS = 1_000_000
MAX_TEXT_CHARS = 32_768
MAX_TIMEOUT_MS = 600_000


def require_canonical_id(value: Any, *, field: str, code: str = INVALID_SANDBOX_ID) -> str:
    if not isinstance(value, str):
        raise RequestValidationError(code, f"{field} must be a canonical string id", field=field)
    candidate = value.strip()
    if not CANONICAL_ID_RE.fullmatch(candidate):
        raise RequestValidationError(code, f"{field} must be a canonical string id", field=field)
    return candidate


def require_provider_id(value: Any, *, field: str = "provider_id") -> str:
    return require_canonical_id(value, field=field, code=INVALID_PROVIDER_ID)


def validate_workspace_relative_path(value: Any, *, field: str = "path", default: str = ".") -> str:
    if value is None:
        value = default
    if not isinstance(value, str):
        raise RequestValidationError(INVALID_EXEC_REQUEST, f"{field} must be a workspace-relative path", field=field)
    candidate = value.strip() or default
    if "\x00" in candidate or "\\" in candidate or candidate.startswith("~"):
        raise RequestValidationError(INVALID_EXEC_REQUEST, f"{field} must be a workspace-relative path", field=field)
    posix = PurePosixPath(candidate)
    windows = PureWindowsPath(candidate)
    if posix.is_absolute() or windows.is_absolute():
        raise RequestValidationError(INVALID_EXEC_REQUEST, f"{field} must not be an absolute host path", field=field)
    if ".." in posix.parts:
        raise RequestValidationError(INVALID_EXEC_REQUEST, f"{field} must not contain parent traversal", field=field)
    return "." if candidate == "." else posix.as_posix().rstrip("/")


def validate_url(value: Any, *, field: str = "url") -> str:
    if not isinstance(value, str):
        raise RequestValidationError(INVALID_EXEC_REQUEST, f"{field} must be an http or https URL", field=field)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RequestValidationError(INVALID_EXEC_REQUEST, f"{field} must be an http or https URL", field=field)
    return value


def validate_exec_payload(
    payload: Mapping[str, Any],
    *,
    require_request_id: bool = True,
    max_timeout_ms: int = MAX_TIMEOUT_MS,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise RequestValidationError(INVALID_EXEC_REQUEST, "Exec request body must be an object")
    if "command" in payload:
        raise RequestValidationError(
            RAW_COMMAND_REJECTED,
            "Public sandbox exec requests must use argv and cannot include a raw command string",
            field="command",
        )

    argv_value = payload.get("argv")
    if isinstance(argv_value, str):
        raise RequestValidationError(INVALID_EXEC_REQUEST, "argv must be an array of argument strings", field="argv")
    if not isinstance(argv_value, (list, tuple)) or not argv_value:
        raise RequestValidationError(INVALID_EXEC_REQUEST, "argv must be a non-empty array", field="argv")
    if len(argv_value) > MAX_ARGV_ITEMS:
        raise RequestValidationError(INVALID_EXEC_REQUEST, "argv has too many arguments", field="argv")

    argv: list[str] = []
    for index, item in enumerate(argv_value):
        if not isinstance(item, str) or not item or "\x00" in item or len(item) > MAX_ARG_LENGTH:
            raise RequestValidationError(
                INVALID_EXEC_REQUEST,
                "argv items must be non-empty strings without NUL bytes",
                field=f"argv[{index}]",
            )
        argv.append(item)

    env_value = payload.get("env") or {}
    if not isinstance(env_value, Mapping):
        raise RequestValidationError(INVALID_EXEC_REQUEST, "env must be an object of string values", field="env")
    if len(env_value) > MAX_ENV_ITEMS:
        raise RequestValidationError(INVALID_EXEC_REQUEST, "env has too many variables", field="env")
    env: dict[str, str] = {}
    for key, value in env_value.items():
        if not isinstance(key, str) or not ENV_KEY_RE.fullmatch(key):
            raise RequestValidationError(INVALID_EXEC_REQUEST, "env keys must be simple variable names", field="env")
        if not isinstance(value, str) or "\x00" in value:
            raise RequestValidationError(INVALID_EXEC_REQUEST, "env values must be strings without NUL bytes", field=key)
        env[key] = value

    timeout_raw = payload.get("timeout_ms", 60_000)
    if isinstance(timeout_raw, bool):
        raise RequestValidationError(INVALID_EXEC_REQUEST, "timeout_ms must be an integer", field="timeout_ms")
    try:
        timeout_ms = int(timeout_raw)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError(INVALID_EXEC_REQUEST, "timeout_ms must be an integer", field="timeout_ms") from exc
    if timeout_ms < 1 or timeout_ms > max_timeout_ms:
        raise RequestValidationError(
            INVALID_EXEC_REQUEST,
            f"timeout_ms must be between 1 and {max_timeout_ms}",
            field="timeout_ms",
        )

    stdin = payload.get("stdin")
    if stdin is not None and (not isinstance(stdin, str) or len(stdin) > MAX_STDIN_CHARS or "\x00" in stdin):
        raise RequestValidationError(INVALID_EXEC_REQUEST, "stdin must be a bounded string", field="stdin")

    request_id = payload.get("client_request_id")
    if request_id is None and require_request_id:
        raise RequestValidationError(INVALID_EXEC_REQUEST, "client_request_id is required", field="client_request_id")
    if request_id is not None:
        request_id = require_canonical_id(request_id, field="client_request_id", code=INVALID_EXEC_REQUEST)

    return {
        "argv": tuple(argv),
        "cwd": validate_workspace_relative_path(payload.get("cwd", "."), field="cwd"),
        "env": env,
        "timeout_ms": timeout_ms,
        "stdin": stdin,
        "client_request_id": request_id,
    }


def validate_desktop_input_payload(
    payload: Mapping[str, Any],
    *,
    width: int | None = None,
    height: int | None = None,
    require_lease: bool = True,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise RequestValidationError(INVALID_DESKTOP_INPUT, "Desktop input request body must be an object")

    action = payload.get("action")
    if action not in DESKTOP_ACTIONS:
        if action is None and "text" in payload:
            raise RequestValidationError(
                INVALID_DESKTOP_INPUT,
                "action is required; to type text use action=type_text with text, then action=key with key=Enter if needed",
                field="action",
            )
        raise RequestValidationError(INVALID_DESKTOP_INPUT, "Unsupported desktop input action", field="action")

    client_action_id = require_canonical_id(
        payload.get("client_action_id"),
        field="client_action_id",
        code=INVALID_DESKTOP_INPUT,
    )

    lease_token = payload.get("lease_token")
    if require_lease and (not isinstance(lease_token, str) or not lease_token):
        raise RequestValidationError(
            DESKTOP_LEASE_REQUIRED,
            "A valid desktop control lease is required",
            field="lease_token",
            status_code=409,
        )
    if lease_token is not None and (not isinstance(lease_token, str) or "\x00" in lease_token):
        raise RequestValidationError(INVALID_DESKTOP_INPUT, "lease_token must be an opaque string", field="lease_token")

    sanitized: dict[str, Any] = {
        "action": action,
        "client_action_id": client_action_id,
        "lease_token": lease_token,
    }

    if action in {"move", "click", "double_click", "drag", "scroll"}:
        sanitized["x"] = _coordinate(payload.get("x"), "x", width)
        sanitized["y"] = _coordinate(payload.get("y"), "y", height)
    if action == "drag":
        sanitized["to_x"] = _coordinate(payload.get("to_x"), "to_x", width)
        sanitized["to_y"] = _coordinate(payload.get("to_y"), "to_y", height)
    if action in {"click", "double_click", "drag"}:
        button = payload.get("button", "left")
        if button not in DESKTOP_BUTTONS:
            raise RequestValidationError(INVALID_DESKTOP_INPUT, "Unsupported pointer button", field="button")
        sanitized["button"] = button
    if action == "scroll":
        sanitized["delta_x"] = _bounded_int(payload.get("delta_x", 0), "delta_x", minimum=-100, maximum=100)
        sanitized["delta_y"] = _bounded_int(payload.get("delta_y", 0), "delta_y", minimum=-100, maximum=100)
        if sanitized["delta_x"] == 0 and sanitized["delta_y"] == 0:
            raise RequestValidationError(INVALID_DESKTOP_INPUT, "scroll requires a non-zero delta", field="delta_y")
    if action == "type_text":
        text = payload.get("text")
        if not isinstance(text, str) or "\x00" in text or len(text) > MAX_TEXT_CHARS:
            raise RequestValidationError(INVALID_DESKTOP_INPUT, "text must be a bounded string", field="text")
        sanitized["text"] = text
    if action == "key":
        key = payload.get("key")
        if not isinstance(key, str) or not key or "\x00" in key or len(key) > 128:
            raise RequestValidationError(INVALID_DESKTOP_INPUT, "key must be a bounded string", field="key")
        sanitized["key"] = key

    return sanitized


def desktop_input_audit_fields(input_payload: Mapping[str, Any]) -> dict[str, Any]:
    audit: dict[str, Any] = {
        "action": input_payload.get("action"),
        "client_action_id": input_payload.get("client_action_id"),
    }
    for field in ("x", "y", "to_x", "to_y", "button", "delta_x", "delta_y", "key"):
        if field in input_payload:
            audit[field] = input_payload[field]
    return audit


def _coordinate(value: Any, field: str, limit: int | None) -> int:
    coordinate = _bounded_int(value, field, minimum=0, maximum=None)
    if limit is not None and coordinate >= limit:
        raise RequestValidationError(INVALID_DESKTOP_INPUT, f"{field} is outside the desktop bounds", field=field)
    return coordinate


def _bounded_int(value: Any, field: str, *, minimum: int, maximum: int | None) -> int:
    if isinstance(value, bool):
        raise RequestValidationError(INVALID_DESKTOP_INPUT, f"{field} must be an integer", field=field)
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError(INVALID_DESKTOP_INPUT, f"{field} must be an integer", field=field) from exc
    if integer < minimum or (maximum is not None and integer > maximum):
        raise RequestValidationError(INVALID_DESKTOP_INPUT, f"{field} is outside the allowed range", field=field)
    return integer
