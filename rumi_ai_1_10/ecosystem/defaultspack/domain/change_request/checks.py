from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from domain.coding.workspace_jail import WorkspaceJail

from .models import CHECK_LOG_TAIL_CHARS


CHECK_TIMEOUT_SECONDS = 120
SHELL_MARKERS = (";", "&&", "||", "|", ">", "<", "`", "$(", "${")
WRITE_FLAGS = {
    "--fix",
    "--write",
    "--update-snapshots",
    "--snapshot-update",
    "--bless",
    "-w",
}
ALLOWED_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("npm", "test"),
    ("npm", "run", "test"),
    ("npm", "run", "lint"),
    ("npm", "run", "build"),
    ("pnpm", "test"),
    ("pnpm", "run", "test"),
    ("pnpm", "run", "lint"),
    ("pnpm", "run", "build"),
    ("yarn", "test"),
    ("yarn", "lint"),
    ("yarn", "build"),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("pytest",),
    ("cargo", "test"),
)


def suggested_checks_for(workspace_root: str, snapshot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    root = Path(workspace_root).expanduser().resolve()
    paths = _snapshot_paths(snapshot)
    suggestions: list[dict[str, Any]] = []
    package_json = root / "package.json"
    if package_json.is_file():
        scripts = _package_scripts(package_json)
        for script in ("test", "lint", "build"):
            if script in scripts:
                suggestions.append(_suggestion(f"npm run {script}", f"npm {script}", paths))
        if "test" not in scripts and _has_path(paths, (".js", ".jsx", ".ts", ".tsx")):
            suggestions.append(_suggestion("npm test", "npm test", paths))
    if _looks_like_python(root, paths):
        suggestions.append(_suggestion("python -m pytest", "pytest", paths))
    if (root / "Cargo.toml").is_file() or _has_path(paths, (".rs",)):
        suggestions.append(_suggestion("cargo test", "cargo test", paths))
    if not suggestions:
        suggestions.append(_suggestion("python -m pytest", "pytest", paths))
    deduped: dict[str, dict[str, Any]] = {}
    for item in suggestions:
        deduped[item["command"]] = item
    return list(deduped.values())


def run_allowed_check(workspace_root: str, command: Any, *, cwd: str | None = None) -> dict[str, Any]:
    args = validate_check_command(command)
    check_cwd = resolve_check_cwd(workspace_root, cwd)
    started = _utc_now()
    start = time.monotonic()
    try:
        completed = subprocess.run(
            args,
            cwd=str(check_cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=CHECK_TIMEOUT_SECONDS,
        )
        duration = int((time.monotonic() - start) * 1000)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        full_log = _full_log(stdout, stderr)
        status = "passed" if completed.returncode == 0 else "failed"
        return {
            "name": " ".join(args[:3]) if args[:2] == ["npm", "run"] else " ".join(args[:2]),
            "command": " ".join(args),
            "status": status,
            "exit_code": completed.returncode,
            "stdout_tail": _tail(stdout),
            "stderr_tail": _tail(stderr),
            "log_tail": _tail(full_log),
            "_full_log": full_log,
            "started_at": started,
            "completed_at": _utc_now(),
            "duration_ms": duration,
            "cwd": _relative_cwd(workspace_root, check_cwd),
        }
    except subprocess.TimeoutExpired as exc:
        duration = int((time.monotonic() - start) * 1000)
        stdout = _decode_timeout_stream(exc.stdout)
        stderr = _decode_timeout_stream(exc.stderr)
        full_log = _full_log(stdout, stderr)
        return {
            "name": " ".join(args[:3]) if args[:2] == ["npm", "run"] else " ".join(args[:2]),
            "command": " ".join(args),
            "status": "timed_out",
            "exit_code": None,
            "stdout_tail": _tail(stdout),
            "stderr_tail": _tail(stderr),
            "log_tail": _tail(full_log),
            "_full_log": full_log,
            "started_at": started,
            "completed_at": _utc_now(),
            "duration_ms": duration,
            "cwd": _relative_cwd(workspace_root, check_cwd),
        }


def validate_check_command(command: Any) -> list[str]:
    if isinstance(command, (list, tuple)):
        args = [str(item).strip() for item in command if str(item).strip()]
    else:
        text = str(command or "").strip()
        if any(marker in text for marker in SHELL_MARKERS):
            raise ValueError("check command contains unsupported shell syntax")
        args = shlex.split(text)
    if not args:
        raise ValueError("check command is required")
    if any("\x00" in arg for arg in args):
        raise ValueError("check command contains invalid arguments")
    for arg in args:
        if arg in WRITE_FLAGS or any(arg.startswith(flag + "=") for flag in WRITE_FLAGS):
            raise ValueError("check command cannot use write-like flags")
    normalized = tuple(args)
    for prefix in ALLOWED_PREFIXES:
        if normalized[: len(prefix)] == prefix:
            _validate_extra_args(args[len(prefix) :])
            return args
    raise ValueError("check command is not in the Rumi Review allowlist")


def resolve_check_cwd(workspace_root: str, cwd: str | None) -> Path:
    root = Path(workspace_root).expanduser().resolve()
    if not cwd:
        return root
    jail = WorkspaceJail(root)
    resolved = jail.resolve(str(cwd), allow_absolute=True)
    rel = jail.relative(resolved)
    reason = jail.restriction_reason(rel)
    if reason:
        raise ValueError("check cwd is restricted: " + reason)
    return Path(resolved)


def _validate_extra_args(args: list[str]) -> None:
    for arg in args:
        if arg in {";", "&&", "||", "|", ">", "<"}:
            raise ValueError("check command contains unsupported shell syntax")
        if str(arg).startswith(("../", "~/")) or os.path.isabs(str(arg)):
            raise ValueError("check command arguments must stay inside the workspace")


def _snapshot_paths(snapshot: dict[str, Any] | None) -> list[str]:
    stats = snapshot.get("file_stats") if isinstance(snapshot, dict) else []
    return [
        str(item.get("path") or "")
        for item in (stats if isinstance(stats, list) else [])
        if isinstance(item, dict) and item.get("path")
    ]


def _package_scripts(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    scripts = payload.get("scripts") if isinstance(payload, dict) else None
    return {str(key) for key in scripts.keys()} if isinstance(scripts, dict) else set()


def _looks_like_python(root: Path, paths: list[str]) -> bool:
    return (
        (root / "pyproject.toml").is_file()
        or (root / "pytest.ini").is_file()
        or (root / "tests").is_dir()
        or _has_path(paths, (".py",))
    )


def _has_path(paths: list[str], suffixes: tuple[str, ...]) -> bool:
    return any(path.endswith(suffixes) for path in paths)


def _suggestion(command: str, name: str, paths: list[str]) -> dict[str, Any]:
    return {
        "id": command.replace(" ", "_").replace("-", "_"),
        "name": name,
        "command": command,
        "reason": "Suggested from changed files" if paths else "Suggested from workspace files",
    }


def _full_log(stdout: str, stderr: str) -> str:
    if stdout and stderr:
        return stdout + ("\n" if not stdout.endswith("\n") else "") + stderr
    return stdout or stderr


def _tail(text: str) -> str:
    return str(text or "")[-CHECK_LOG_TAIL_CHARS:]


def _decode_timeout_stream(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value or "")


def _relative_cwd(workspace_root: str, cwd: Path) -> str:
    root = Path(workspace_root).expanduser().resolve()
    try:
        rel = cwd.resolve().relative_to(root)
    except ValueError:
        return "."
    text = rel.as_posix()
    return text if text and text != "." else "."


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
