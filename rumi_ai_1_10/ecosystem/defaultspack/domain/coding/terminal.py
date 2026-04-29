"""ターミナル操作ドメインロジック."""

import os
import shlex
import subprocess
import uuid


HIGH_RISK_TOKENS = {"rm", "sudo", "chmod", "chown", "curl", "wget", "git push", "npm install"}
LOW_RISK_TOKENS = {"pwd", "ls", "cat", "head", "tail", "git status", "git diff"}


class Terminal:
    """ワークスペース内でローカルコマンドを実行する。"""

    def __init__(self, workspace_root=None):
        self._history = []
        self._root = os.path.realpath(workspace_root or os.getcwd())

    @property
    def history(self):
        """実行履歴を返す。"""
        return list(self._history)

    def _resolve_cwd(self, cwd):
        if cwd is None or cwd == "":
            return self._root
        resolved = os.path.realpath(cwd if os.path.isabs(cwd) else os.path.join(self._root, cwd))
        if resolved != self._root and not resolved.startswith(self._root + os.sep):
            raise ValueError("cwd is outside workspace root: " + str(cwd))
        return resolved

    def classify(self, command):
        normalized = " ".join(str(command).strip().split())
        if not normalized:
            return {"risk_level": "low", "approval_required": False, "reason": "empty"}
        for token in HIGH_RISK_TOKENS:
            if normalized == token or normalized.startswith(token + " ") or ("; " + token) in normalized:
                return {"risk_level": "high", "approval_required": True, "reason": "high_risk_command"}
        for token in LOW_RISK_TOKENS:
            if normalized == token or normalized.startswith(token + " "):
                return {"risk_level": "low", "approval_required": False, "reason": "read_only_command"}
        return {"risk_level": "medium", "approval_required": True, "reason": "command_execution"}

    def execute(self, command, cwd=None, timeout=30, env=None, approved=False):
        """コマンドを実行する。medium/high risk は approved が必要。"""
        risk = self.classify(command)
        if risk["approval_required"] and not approved:
            return {
                "command": command,
                "approval_required": True,
                "risk": risk,
                "exit_code": None,
                "stdout": "",
                "stderr": "",
            }
        resolved_cwd = self._resolve_cwd(cwd)
        record = {
            "type": "execute",
            "command": command,
            "cwd": resolved_cwd,
            "timeout": timeout,
            "risk": risk,
        }
        self._history.append(record)
        process_env = os.environ.copy()
        if isinstance(env, dict):
            for key, value in env.items():
                process_env[str(key)] = str(value)
        completed = subprocess.run(
            command,
            cwd=resolved_cwd,
            env=process_env,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "command": command,
            "cwd": resolved_cwd,
            "risk": risk,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def stream(self, command, cwd=None, approved=False):
        """長時間実行用のストリーム開始メタデータを返す。

        現時点ではプロセスライフサイクル管理をHTTP越しに保持しないため、
        実行はせず approval/risk つきの stream_id を返す。
        """
        risk = self.classify(command)
        stream_id = str(uuid.uuid4())
        record = {
            "type": "stream",
            "command": command,
            "cwd": self._resolve_cwd(cwd),
            "stream_id": stream_id,
            "risk": risk,
        }
        self._history.append(record)
        return {
            "command": command,
            "stream_id": stream_id,
            "approval_required": risk["approval_required"] and not approved,
            "risk": risk,
            "started": False,
        }
