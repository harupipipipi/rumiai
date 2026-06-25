from __future__ import annotations

import copy
import os
import time
from pathlib import Path
from typing import Any


SECRET_KEY_PARTS = (
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
    "api_key",
    "apikey",
)

NON_SECRET_POLICY_KEYS = {
    "secret_access",
    "secret_use",
    "secrets_access",
}


class AdaptiveError(Exception):
    def __init__(self, code: str, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def now_seconds() -> int:
    return int(time.time())


def clean_profile_id(value: Any) -> str:
    candidate = str(value or "").strip() or "default"
    try:
        from core_runtime.profile_workspace import validate_profile_id

        return validate_profile_id(candidate)
    except ValueError:
        raise
    except Exception:
        if "/" in candidate or "\\" in candidate or ".." in candidate:
            raise ValueError("profile_id must not contain path traversal segments")
        return candidate


def profile_id_from(args: dict[str, Any] | None, ctx: dict[str, Any] | None) -> str:
    args = args if isinstance(args, dict) else {}
    ctx = ctx if isinstance(ctx, dict) else {}
    for value in (
        args.get("profile_id"),
        ctx.get("profile_id"),
        ctx.get("active_startup_profile_id"),
        (ctx.get("active_startup_profile") or {}).get("profile_id")
        if isinstance(ctx.get("active_startup_profile"), dict)
        else None,
    ):
        if str(value or "").strip():
            return clean_profile_id(value)
    try:
        from core_runtime.profile_paths import active_profile_id

        active = active_profile_id()
        if active:
            return clean_profile_id(active)
    except Exception:
        pass
    return "default"


def adaptive_store_root(profile_id: str) -> Path:
    configured = os.environ.get("RUMI_ADAPTIVE_STORE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve() / clean_profile_id(profile_id)
    try:
        from core_runtime.profile_workspace import ProfileWorkspaceManager

        return (
            ProfileWorkspaceManager()
            .profile_user_data_dir(clean_profile_id(profile_id))
            .joinpath("adaptive")
        )
    except Exception:
        base = Path(os.environ.get("RUMI_USER_DATA") or Path.cwd() / "user_data")
        return base / "profiles" / clean_profile_id(profile_id) / "user_data" / "adaptive"


def workspace_root_from(args: dict[str, Any] | None, ctx: dict[str, Any] | None) -> Path:
    args = args if isinstance(args, dict) else {}
    ctx = ctx if isinstance(ctx, dict) else {}
    raw = (
        args.get("workspace_root")
        or args.get("root")
        or ctx.get("workspace_root")
        or ctx.get("root")
        or os.environ.get("RUMI_WORKSPACE_ROOT")
    )
    root = Path(raw).expanduser() if raw else Path.cwd()
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise AdaptiveError("WORKSPACE_NOT_FOUND", f"workspace root not found: {root}")
    return root


def resolve_under(root: Path, value: Any) -> Path:
    rel = str(value or ".").strip() or "."
    candidate = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AdaptiveError("PATH_OUTSIDE_WORKSPACE", "path is outside workspace") from exc
    return candidate


def coerce_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            lowered = text_key.lower()
            if lowered in NON_SECRET_POLICY_KEYS:
                output[text_key] = redact(item)
            elif any(part in lowered for part in SECRET_KEY_PARTS):
                output[text_key] = "[REDACTED]"
            else:
                output[text_key] = redact(item)
        return output
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return copy.deepcopy(value)


def compact_text(value: Any, *, limit: int = 240) -> str:
    text = str(value or "")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."
