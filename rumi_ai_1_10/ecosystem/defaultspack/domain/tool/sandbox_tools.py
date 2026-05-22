from __future__ import annotations

import json
import shlex
import sys
from typing import Any

from domain.coding.terminal import Terminal

from ._agent_os_common import err, now_slug, ok, write_text_file, workspace


def sandbox_exec(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    command = arguments.get("command")
    if not command:
        return err("'command' is required", "INVALID_INPUT")
    try:
        ws = workspace(context)
        terminal = Terminal(str(ws.root))
        result = terminal.execute(command, cwd=arguments.get("cwd"), timeout=int(arguments.get("timeout") or 30), approved=True)
        return ok({"workspace": str(ws.root), **result})
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
        command = [sys.executable, str(script_path)]
        return sandbox_exec({"command": command, "timeout": arguments.get("timeout") or 30}, context)
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
        return sandbox_exec({"command": ["node", str(script_path)], "timeout": arguments.get("timeout") or 30}, context)
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
