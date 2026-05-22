from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from ._agent_os_common import err, ok


def _dry_or_command(arguments: dict[str, Any], command: list[str], label: str) -> dict[str, Any]:
    if arguments.get("execute") is not True:
        return ok({"dry_run": True, "command": command, "tool": label})
    if not command or shutil.which(command[0]) is None:
        return err(f"{command[0] if command else label} is not available", "MISSING_CLI")
    completed = subprocess.run(command, text=True, capture_output=True, timeout=int(arguments.get("timeout") or 60))
    return ok({"command": command, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr})


def github_search(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    query = str(arguments.get("query") or "")
    kind = str(arguments.get("kind") or "repos")
    return _dry_or_command(arguments, ["gh", "search", kind, query, "--limit", str(arguments.get("limit") or 10)], "github_search")


def github_pr_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    command = ["gh", "pr", "create", "--title", str(arguments.get("title") or "PR"), "--body", str(arguments.get("body") or "")]
    if arguments.get("draft", True):
        command.append("--draft")
    return _dry_or_command(arguments, command, "github_pr_create")


def github_issue_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _dry_or_command(arguments, ["gh", "issue", "create", "--title", str(arguments.get("title") or "Issue"), "--body", str(arguments.get("body") or "")], "github_issue_create")


def gmail_search(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok({"connector_required": "gmail", "dry_run": True, "query": arguments.get("query")})


def gmail_draft(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok({"connector_required": "gmail", "dry_run": True, "draft": {k: arguments.get(k) for k in ("to", "subject", "body")}})


def calendar_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok({"connector_required": "calendar", "dry_run": True, "event": dict(arguments)})


def drive_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok({"connector_required": "drive", "dry_run": True, "file": dict(arguments)})


def drive_export(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok({"connector_required": "drive", "dry_run": True, "export": dict(arguments)})


def slack_send(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok({"connector_required": "slack", "dry_run": True, "message": dict(arguments)})


def discord_send(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok({"connector_required": "discord", "dry_run": True, "message": dict(arguments)})


def line_push(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok({"connector_required": "line", "dry_run": True, "message": dict(arguments)})
