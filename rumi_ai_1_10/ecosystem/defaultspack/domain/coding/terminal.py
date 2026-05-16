"""ターミナル操作ドメインロジック."""

import json
import os
import shutil
import shlex
import subprocess
import sys
import time
import uuid

from domain.coding.terminal_policy import classify_command, normalized_command

SHELL_METACHARS = {";", "&&", "||", "|", ">", "<", "`", "$(", "${"}
MAX_OUTPUT_BYTES = 128 * 1024
ENV_ALLOWLIST = {"PATH", "HOME", "USER", "USERNAME", "USERPROFILE", "TEMP", "TMP", "SYSTEMROOT"}
SNAPSHOT_DIR = ".rumi_snapshots"
COMMAND_LOG_FILE = "terminal_log.jsonl"


class Terminal:
    """ワークスペース内でローカルコマンドを実行する。"""

    def __init__(self, workspace_root=None):
        self._history = []
        self._root = os.path.realpath(workspace_root or os.getcwd())

    @property
    def history(self):
        """実行履歴を返す。"""
        return list(self._history)

    def _command_log_path(self):
        return os.path.join(self._root, SNAPSHOT_DIR, COMMAND_LOG_FILE)

    def _record_command(self, record):
        entry = dict(record)
        entry.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self._history.append(entry)
        try:
            log_dir = os.path.dirname(self._command_log_path())
            os.makedirs(log_dir, exist_ok=True)
            with open(self._command_log_path(), "a", encoding="utf-8") as handle:
                json.dump(entry, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
        except Exception:
            pass
        return entry

    def _resolve_cwd(self, cwd):
        if cwd is None or cwd == "":
            return self._root
        resolved = os.path.realpath(cwd if os.path.isabs(cwd) else os.path.join(self._root, cwd))
        if resolved != self._root and not resolved.startswith(self._root + os.sep):
            raise ValueError("cwd is outside workspace root: " + str(cwd))
        return resolved

    def _normalized_command(self, command):
        return normalized_command(command)

    def classify(self, command, cwd=None):
        return classify_command(command, cwd=cwd, workspace_root=self._root)

    def _uses_shell_syntax(self, command):
        if isinstance(command, (list, tuple)):
            return False
        normalized = self._normalized_command(command)
        return any(marker in normalized for marker in SHELL_METACHARS)

    def _command_args(self, command):
        if isinstance(command, (list, tuple)):
            args = [str(item) for item in command]
        else:
            args = shlex.split(str(command), posix=True)
        if args and args[0].lower() in {"python", "python3"}:
            if sys.platform == "win32" or shutil.which(args[0]) is None:
                args[0] = sys.executable
        return args

    def _process_env(self, env):
        process_env = {key: value for key, value in os.environ.items() if key.upper() in ENV_ALLOWLIST}
        if isinstance(env, dict):
            for key, value in env.items():
                key_text = str(key)
                if key_text.upper() in ENV_ALLOWLIST or key_text.startswith("RUMI_"):
                    process_env[key_text] = str(value)
        return process_env

    def _truncate_output(self, text):
        raw = str(text or "").encode("utf-8", errors="replace")
        if len(raw) <= MAX_OUTPUT_BYTES:
            return str(text or "")
        return raw[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") + "\n[output truncated]\n"

    def execute(self, command, cwd=None, timeout=30, env=None, approved=False):
        """コマンドを実行する。medium/high risk は approved が必要。"""
        risk = self.classify(command, cwd=cwd)
        if risk["approval_required"] and (not approved or risk.get("classification") == "blocked"):
            self._record_command({
                "type": "execute",
                "command": command,
                "cwd": cwd,
                "timeout": timeout,
                "risk": risk,
                "approval_required": True,
                "executed": False,
                "exit_code": None,
            })
            blocked = risk.get("classification") == "blocked"
            return {
                "command": command,
                "approval_required": True,
                "classification": risk.get("classification", risk.get("risk_level")),
                "risk_reasons": risk.get("risk_reasons", [risk.get("reason", "command_execution")]),
                "risk": risk,
                "exit_code": None,
                "stdout": "",
                "stderr": "blocked by terminal policy" if blocked else "",
                **({"blocked": True} if blocked else {}),
            }
        resolved_cwd = self._resolve_cwd(cwd)
        normalized_command = self._normalized_command(command)
        if normalized_command == "pwd":
            result = {
                "command": command,
                "cwd": resolved_cwd,
                "risk": risk,
                "classification": risk.get("classification", risk.get("risk_level")),
                "risk_reasons": risk.get("risk_reasons", [risk.get("reason", "read_only_command")]),
                "approval_required": False,
                "exit_code": 0,
                "stdout": resolved_cwd + "\n",
                "stderr": "",
            }
            self._record_command({
                "type": "execute",
                "command": command,
                "cwd": resolved_cwd,
                "timeout": timeout,
                "risk": risk,
                "approval_required": False,
                "executed": True,
                "exit_code": 0,
            })
            return result
        record = {
            "type": "execute",
            "command": command,
            "cwd": resolved_cwd,
            "timeout": timeout,
            "risk": risk,
        }
        use_shell = self._uses_shell_syntax(command)
        args = command if use_shell else self._command_args(command)
        completed = subprocess.run(
            args,
            cwd=resolved_cwd,
            env=self._process_env(env),
            shell=use_shell,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        result = {
            "command": command,
            "cwd": resolved_cwd,
            "risk": risk,
            "classification": risk.get("classification", risk.get("risk_level")),
            "risk_reasons": risk.get("risk_reasons", [risk.get("reason", "command_execution")]),
            "approval_required": False,
            "exit_code": completed.returncode,
            "stdout": self._truncate_output(completed.stdout),
            "stderr": self._truncate_output(completed.stderr),
        }
        record.update({
            "approval_required": False,
            "executed": True,
            "exit_code": completed.returncode,
        })
        self._record_command(record)
        return result

    def stream(self, command, cwd=None, timeout=30, approved=False):
        """長時間実行用のストリーム開始メタデータを返す。

        現時点ではプロセスライフサイクル管理をHTTP越しに保持しないため、
        実行はせず approval/risk つきの stream_id を返す。
        """
        risk = self.classify(command, cwd=cwd)
        if risk["approval_required"] and (not approved or risk.get("classification") == "blocked"):
            self._record_command({
                "type": "stream",
                "command": command,
                "cwd": cwd,
                "timeout": timeout,
                "risk": risk,
                "approval_required": True,
                "executed": False,
                "started": False,
            })
            blocked = risk.get("classification") == "blocked"
            return {
                "command": command,
                "approval_required": True,
                "classification": risk.get("classification", risk.get("risk_level")),
                "risk_reasons": risk.get("risk_reasons", [risk.get("reason", "command_execution")]),
                "risk": risk,
                "started": False,
                **({"blocked": True} if blocked else {}),
            }
        stream_id = str(uuid.uuid4())
        resolved_cwd = self._resolve_cwd(cwd)
        normalized_command = self._normalized_command(command)
        if normalized_command == "pwd":
            result = {
                "command": command,
                "cwd": resolved_cwd,
                "stream_id": stream_id,
                "approval_required": False,
                "risk": risk,
                "classification": risk.get("classification", risk.get("risk_level")),
                "risk_reasons": risk.get("risk_reasons", [risk.get("reason", "read_only_command")]),
                "started": True,
                "exit_code": 0,
                "stdout": resolved_cwd + "\n",
                "stderr": "",
                "timed_out": False,
            }
            self._record_command({
                "type": "stream",
                "command": command,
                "cwd": resolved_cwd,
                "timeout": timeout,
                "stream_id": stream_id,
                "risk": risk,
                "approval_required": False,
                "executed": True,
                "started": True,
                "exit_code": 0,
                "timed_out": False,
            })
            return result
        record = {
            "type": "stream",
            "command": command,
            "cwd": resolved_cwd,
            "timeout": timeout,
            "stream_id": stream_id,
            "risk": risk,
        }
        use_shell = self._uses_shell_syntax(command)
        args = command if use_shell else self._command_args(command)
        process = subprocess.Popen(
            args,
            cwd=resolved_cwd,
            env=self._process_env(None),
            shell=use_shell,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            timed_out = True
        result = {
            "command": command,
            "cwd": resolved_cwd,
            "stream_id": stream_id,
            "approval_required": False,
            "risk": risk,
            "classification": risk.get("classification", risk.get("risk_level")),
            "risk_reasons": risk.get("risk_reasons", [risk.get("reason", "command_execution")]),
            "started": True,
            "exit_code": process.returncode,
            "stdout": self._truncate_output(stdout),
            "stderr": self._truncate_output(stderr),
            "timed_out": timed_out,
        }
        record.update({
            "approval_required": False,
            "executed": True,
            "started": True,
            "exit_code": process.returncode,
            "timed_out": timed_out,
        })
        self._record_command(record)
        return result
