from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import uuid
from typing import Any

from core_runtime.docker_run_builder import DockerRunBuilder
from domain.coding.terminal import Terminal

from ._agent_os_common import err, now_slug, ok, write_text_file, workspace

DEFAULT_SANDBOX_IMAGE = os.environ.get("RUMI_SANDBOX_IMAGE") or "python:3.11-slim"
DEFAULT_NODE_SANDBOX_IMAGE = os.environ.get("RUMI_NODE_SANDBOX_IMAGE") or "node:22-bookworm-slim"
MAX_SANDBOX_OUTPUT = 1024 * 1024

_IMAGE_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
_DOMAIN_COMPONENT = r"(?:[a-z0-9]|[a-z0-9][a-z0-9-]*[a-z0-9])"
_DOMAIN = rf"{_DOMAIN_COMPONENT}(?:\.{_DOMAIN_COMPONENT})*(?::[0-9]+)?"
_TAG = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}"
_DIGEST_ALGORITHM = r"[A-Za-z][A-Za-z0-9]*(?:[+._-][A-Za-z][A-Za-z0-9]*)*"
_DIGEST = rf"{_DIGEST_ALGORITHM}:[0-9a-fA-F]{{32,}}"
_DOCKER_IMAGE_REF_RE = re.compile(
    rf"^(?=.{{1,255}}$)(?:(?:{_DOMAIN})/)?"
    rf"{_IMAGE_COMPONENT}(?:/{_IMAGE_COMPONENT})*"
    rf"(?::{_TAG})?(?:@{_DIGEST})?$"
)


def _normalize_command(command: Any) -> list[str]:
    if isinstance(command, str):
        return ["sh", "-lc", command]
    if isinstance(command, (list, tuple)) and command:
        return [str(part) for part in command]
    raise ValueError("'command' must be a non-empty string or array")


def _validate_docker_image_ref(image: Any) -> str:
    image_ref = str(image or "")
    if image_ref != image_ref.strip() or not _DOCKER_IMAGE_REF_RE.fullmatch(image_ref):
        raise ValueError("invalid Docker image reference")
    return image_ref


def _container_workdir(ws: Any, cwd: Any) -> str:
    resolved = ws.resolve(str(cwd or "."), must_exist=False, allow_root=True)
    relative = ws.relative(resolved) if resolved != ws.root else ""
    return "/workspace" + (("/" + relative) if relative else "")


def _run_in_docker(*, ws: Any, command: Any, cwd: Any, timeout: int, image: str) -> dict[str, Any]:
    container_command = _normalize_command(command)
    container_name = f"rumi-sandbox-{uuid.uuid4().hex[:12]}"
    docker_cmd = (
        DockerRunBuilder(name=container_name)
        .pids_limit(100)
        .user(f"{os.getuid()}:{os.getgid()}")
        .volume(f"{ws.root.resolve()}:/workspace:rw")
        .workdir(_container_workdir(ws, cwd))
        .label("rumi.managed", "true")
        .label("rumi.type", "artifact_sandbox_exec")
        .image(image)
        .command(container_command)
        .build()
    )
    completed = subprocess.run(
        docker_cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    stdout = completed.stdout[:MAX_SANDBOX_OUTPUT]
    stderr = completed.stderr[:MAX_SANDBOX_OUTPUT]
    if len(completed.stdout) > MAX_SANDBOX_OUTPUT:
        stdout += "\n[stdout truncated]"
    if len(completed.stderr) > MAX_SANDBOX_OUTPUT:
        stderr += "\n[stderr truncated]"
    return {
        "command": command,
        "cwd": _container_workdir(ws, cwd),
        "containerized": True,
        "image": image,
        "network": "none",
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def sandbox_exec(arguments: dict[str, Any], context: dict[str, Any] | None = None, *, image: Any | None = None) -> dict[str, Any]:
    command = arguments.get("command")
    if not command:
        return err("'command' is required", "INVALID_INPUT")
    if image is None and "image" in arguments:
        return err("'image' is not accepted for sandbox_exec", "INVALID_SANDBOX_IMAGE")
    try:
        ws = workspace(context)
        terminal = Terminal(str(ws.root))
        risk = terminal.classify(command, cwd=arguments.get("cwd"))
        if risk.get("classification") == "blocked":
            return err("command is blocked by terminal policy", "SANDBOX_COMMAND_BLOCKED", risk=risk)
        image = _validate_docker_image_ref(image or DEFAULT_SANDBOX_IMAGE)
        result = _run_in_docker(
            ws=ws,
            command=command,
            cwd=arguments.get("cwd"),
            timeout=int(arguments.get("timeout") or 30),
            image=image,
        )
        return ok({"workspace": str(ws.root), "risk": risk, **result})
    except FileNotFoundError as exc:
        if getattr(exc, "filename", None) == "docker":
            return err("Docker is required for sandbox execution and is not available", "SANDBOX_UNAVAILABLE")
        return err(str(exc), "SANDBOX_EXEC_FAILED")
    except subprocess.TimeoutExpired:
        return err("sandbox execution timed out", "SANDBOX_TIMEOUT")
    except ValueError as exc:
        if str(exc) == "invalid Docker image reference":
            return err(str(exc), "INVALID_SANDBOX_IMAGE")
        return err(str(exc), "SANDBOX_EXEC_FAILED")
    except Exception as exc:
        return err(str(exc), "SANDBOX_EXEC_FAILED")


def python_exec(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    code = arguments.get("code")
    script_path = arguments.get("script_path")
    if not code and not script_path:
        return err("'code' or 'script_path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        if code:
            script = ws.resolve(f".sandbox/python-{now_slug()}.py")
            write_text_file(script, str(code))
            script_path = ws.relative(script)
        else:
            script_path = ws.relative(ws.resolve(str(script_path), must_exist=True))
        command = ["python", str(script_path)]
        return sandbox_exec(
            {"command": command, "timeout": arguments.get("timeout") or 30},
            context,
            image=DEFAULT_SANDBOX_IMAGE,
        )
    except Exception as exc:
        return err(str(exc), "PYTHON_EXEC_FAILED")


def node_exec(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    code = arguments.get("code")
    script_path = arguments.get("script_path")
    if not code and not script_path:
        return err("'code' or 'script_path' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        if code:
            script = ws.resolve(f".sandbox/node-{now_slug()}.js")
            write_text_file(script, str(code))
            script_path = ws.relative(script)
        else:
            script_path = ws.relative(ws.resolve(str(script_path), must_exist=True))
        return sandbox_exec(
            {"command": ["node", str(script_path)], "timeout": arguments.get("timeout") or 30},
            context,
            image=DEFAULT_NODE_SANDBOX_IMAGE,
        )
    except Exception as exc:
        return err(str(exc), "NODE_EXEC_FAILED")


def package_install_plan(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    packages = arguments.get("packages")
    manager = str(arguments.get("manager") or "pip").lower()
    if isinstance(packages, str):
        packages = shlex.split(packages)
    if not isinstance(packages, list):
        packages = []
    command = {
        "pip": [sys.executable, "-m", "pip", "install", *packages],
        "npm": ["npm", "install", *packages],
        "pnpm": ["pnpm", "add", *packages],
    }.get(manager, [manager, *packages])
    return ok({"manager": manager, "packages": packages, "command": command, "executes": False})
