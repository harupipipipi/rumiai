from __future__ import annotations

import ntpath
import os
import shlex
import sys
from dataclasses import dataclass
from typing import Any


LOW_RISK_PREFIXES = {
    "git status",
    "git diff",
    "git log",
    "git show",
    "ls",
    "dir",
    "pwd",
    "cat",
    "head",
    "tail",
    "pytest",
    "python -m pytest",
    "python3 -m pytest",
    "npm test",
    "npm run test",
}

INSTALL_COMMANDS = {
    "npm install",
    "npm i",
    "pnpm install",
    "yarn add",
    "pip install",
    "pip3 install",
    "python -m pip install",
    "python3 -m pip install",
    "uv pip install",
    "cargo install",
    "brew install",
}

NETWORK_COMMANDS = {
    "curl",
    "wget",
    "Invoke-WebRequest",
    "Invoke-RestMethod",
    "iwr",
    "irm",
    "ssh",
    "scp",
    "rsync",
    "git clone",
    "git fetch",
    "git pull",
    "git push",
}

DESTRUCTIVE_COMMANDS = {
    "rm",
    "rmdir",
    "del",
    "erase",
    "Remove-Item",
    "rd",
    "git reset",
    "git clean",
    "git checkout",
    "git switch",
    "git branch -D",
    "chmod",
    "chown",
    "sudo",
}

CREDENTIAL_COMMANDS = {
    "gh auth",
    "git credential",
    "security find-generic-password",
    "pass",
    "op read",
    "aws configure",
}

SHELL_ESCAPE_MARKERS = (";", "&&", "||", "|", ">", "<", "`", "$(", "${")
DOWNLOAD_EXEC_MARKERS = (
    "| sh",
    "| bash",
    "| zsh",
    "| powershell",
    "| pwsh",
    "iex ",
    "Invoke-Expression",
)


@dataclass(frozen=True)
class TerminalPolicyDecision:
    classification: str
    approval_required: bool
    risk_reasons: tuple[str, ...]
    primary_reason: str
    paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "risk_level": self.classification,
            "approval_required": self.approval_required,
            "risk_reasons": list(self.risk_reasons),
            "reason": self.primary_reason,
            **({"paths": list(self.paths)} if self.paths else {}),
        }


def normalized_command(command: Any) -> str:
    if isinstance(command, (list, tuple)):
        return " ".join(str(item).strip() for item in command if str(item).strip())
    return " ".join(str(command).strip().split())


def inspection_args(command: Any) -> list[str]:
    if isinstance(command, (list, tuple)):
        return [str(item) for item in command]
    return shlex.split(str(command), posix=sys.platform != "win32")


def _starts_with_any(normalized: str, candidates: set[str]) -> str | None:
    lower = normalized.lower()
    for candidate in sorted(candidates, key=len, reverse=True):
        candidate_lower = candidate.lower()
        if lower == candidate_lower or lower.startswith(candidate_lower + " "):
            return candidate
    return None


def _low_risk_prefix(normalized: str) -> str | None:
    return _starts_with_any(normalized, LOW_RISK_PREFIXES)


def _path_arg_may_escape_workspace(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or text == "--" or text.startswith("-") or text.isdigit():
        return False
    normalized = text.replace("\\", "/")
    return (
        os.path.isabs(os.path.expanduser(text))
        or ntpath.isabs(text)
        or normalized == ".."
        or normalized.startswith("../")
        or normalized.endswith("/..")
        or "/../" in normalized
    )


def _path_arg_inside_workspace(value: Any, cwd: str, workspace_root: str) -> bool:
    text = str(value or "")
    if ntpath.isabs(text) and not os.path.isabs(text):
        return False
    expanded = os.path.expanduser(text)
    resolved = os.path.realpath(expanded if os.path.isabs(expanded) else os.path.join(cwd, expanded))
    root = os.path.realpath(workspace_root)
    return resolved == root or resolved.startswith(root + os.sep)


def _resolve_cwd(cwd: str | None, workspace_root: str) -> str:
    root = os.path.realpath(workspace_root)
    if cwd is None or cwd == "":
        return root
    resolved = os.path.realpath(cwd if os.path.isabs(cwd) else os.path.join(root, cwd))
    if resolved != root and not resolved.startswith(root + os.sep):
        return root
    return resolved


def _outside_workspace_read_args(command: Any, cwd: str | None, low_risk_token: str, workspace_root: str) -> list[str]:
    try:
        args = inspection_args(command)
    except ValueError:
        return []
    resolved_cwd = _resolve_cwd(cwd, workspace_root)
    remaining = args[len(low_risk_token.split()):]
    outside = []
    for arg in remaining:
        if _path_arg_may_escape_workspace(arg) and not _path_arg_inside_workspace(arg, resolved_cwd, workspace_root):
            outside.append(str(arg))
    return outside


def classify_command(command: Any, *, cwd: str | None = None, workspace_root: str | None = None) -> dict[str, Any]:
    normalized = normalized_command(command)
    if not normalized:
        return TerminalPolicyDecision("low", False, ("empty",), "empty").to_dict()

    reasons: list[str] = []
    if any(marker in normalized for marker in SHELL_ESCAPE_MARKERS):
        reasons.append("shell_escape")
    if any(marker.lower() in normalized.lower() for marker in DOWNLOAD_EXEC_MARKERS):
        reasons.append("download_exec_pipe")
    if _starts_with_any(normalized, INSTALL_COMMANDS):
        reasons.append("install")
    if _starts_with_any(normalized, NETWORK_COMMANDS):
        reasons.append("network")
    if _starts_with_any(normalized, DESTRUCTIVE_COMMANDS):
        reasons.append("destructive")
    if _starts_with_any(normalized, CREDENTIAL_COMMANDS):
        reasons.append("credential")

    low_risk_token = _low_risk_prefix(normalized)
    if low_risk_token:
        outside_paths: list[str] = []
        if workspace_root:
            outside_paths = _outside_workspace_read_args(command, cwd, low_risk_token, workspace_root)
        if outside_paths:
            return TerminalPolicyDecision(
                "high",
                True,
                ("outside_workspace_path",),
                "outside_workspace_path",
                tuple(outside_paths),
            ).to_dict()
        if not reasons:
            return TerminalPolicyDecision("low", False, ("read_only_command",), "read_only_command").to_dict()

    if "download_exec_pipe" in reasons:
        classification = "blocked"
    elif any(reason in reasons for reason in ("destructive", "network", "install", "credential", "shell_escape")):
        classification = "high"
    else:
        classification = "medium"
        reasons.append("command_execution")

    return TerminalPolicyDecision(
        classification,
        True,
        tuple(dict.fromkeys(reasons)),
        reasons[0],
    ).to_dict()
