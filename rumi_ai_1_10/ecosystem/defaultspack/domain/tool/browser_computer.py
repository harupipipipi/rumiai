from __future__ import annotations

import json
import platform
import secrets
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any


class BrowserComputerController:
    """Generic browser/computer action controller with approval gates."""

    def __init__(self, artifact_root: Path | None = None) -> None:
        pack_root = Path(__file__).resolve().parents[2]
        self._artifact_root = artifact_root or pack_root / "user_data" / "artifacts" / "computer"
        self._session_path = pack_root / "user_data" / "shared" / "browser_sessions.json"
        self._approval_path = pack_root / "user_data" / "shared" / "browser_computer_approvals.json"

    def run(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if action == "browser.open_url":
            return self._open_url(str(payload.get("url", "")), payload=payload, dry_run=bool(payload.get("dry_run")))
        if action == "browser.session":
            return {"action": action, "session": self._read_sessions()}
        if action == "computer.screenshot":
            return self._screenshot(payload=payload, dry_run=bool(payload.get("dry_run")))
        if action in {"computer.click", "computer.type", "computer.key", "computer.scroll"}:
            return self._desktop_action(action, payload)
        raise ValueError(f"Unsupported browser/computer action: {action}")

    def _open_url(self, url: str, *, payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        if not url.startswith(("http://", "https://", "file://")):
            raise ValueError("'url' must start with http://, https://, or file://")
        if dry_run:
            return {"action": "browser.open_url", "url": url, "dry_run": True, "requires_approval": False}
        approved = self._consume_approval(payload, "browser.open_url", {"url": url})
        if not approved:
            return self._approval_required("browser.open_url", {"url": url})
        webbrowser.open(url)
        sessions = self._read_sessions()
        sessions["last_url"] = url
        sessions["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._write_sessions(sessions)
        return {"action": "browser.open_url", "url": url, "opened": True}

    def _screenshot(self, *, payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        if dry_run:
            return {"action": "computer.screenshot", "dry_run": True, "requires_approval": False}
        approved = self._consume_approval(payload, "computer.screenshot", {})
        if not approved:
            return self._approval_required("computer.screenshot", {})
        if platform.system() != "Darwin":
            return {"action": "computer.screenshot", "supported": False, "reason": "macOS screencapture is required."}
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        path = self._artifact_root / f"screenshot-{int(time.time() * 1000)}.png"
        subprocess.run(["screencapture", "-x", str(path)], check=True)
        return {"action": "computer.screenshot", "path": str(path), "mime_type": "image/png"}

    def _desktop_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(payload.get("dry_run"))
        if dry_run:
            return {"action": action, "dry_run": True, "requires_approval": False, "payload": payload}
        approval_payload = self._safe_payload(payload)
        if not self._consume_approval(payload, action, approval_payload):
            return self._approval_required(action, approval_payload)
        if platform.system() != "Darwin":
            return {"action": action, "supported": False, "reason": "AppleScript desktop control is only supported on macOS."}
        script = self._apple_script(action, payload)
        subprocess.run(["osascript", "-e", script], check=True)
        return {"action": action, "executed": True}

    def _apple_script(self, action: str, payload: dict[str, Any]) -> str:
        if action == "computer.click":
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
            return f'tell application "System Events" to click at {{{x}, {y}}}'
        if action == "computer.type":
            text = json.dumps(str(payload.get("text", "")))
            return f'tell application "System Events" to keystroke {text}'
        if action == "computer.key":
            key = payload.get("key", "return")
            if isinstance(key, int):
                return f'tell application "System Events" to key code {key}'
            return f'tell application "System Events" to keystroke {json.dumps(str(key))}'
        if action == "computer.scroll":
            amount = int(payload.get("amount", 1))
            return f'tell application "System Events" to scroll wheel {amount}'
        raise ValueError(action)

    def _read_sessions(self) -> dict[str, Any]:
        try:
            value = json.loads(self._session_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _write_sessions(self, value: dict[str, Any]) -> None:
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def _approval_required(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = self._issue_approval(action, payload)
        return {
            "action": action,
            "requires_approval": True,
            "approval_token": token,
            "approval_expires_in_seconds": 300,
            "approval_hint": "Repeat the same action with payload.approval_token after an explicit user confirmation.",
            "payload": payload,
        }

    def _issue_approval(self, action: str, payload: dict[str, Any]) -> str:
        approvals = self._read_approvals()
        token = secrets.token_urlsafe(24)
        approvals[token] = {
            "action": action,
            "payload": payload,
            "expires_at": time.time() + 300,
        }
        self._write_approvals(approvals)
        return token

    def _consume_approval(self, payload: dict[str, Any], action: str, expected_payload: dict[str, Any]) -> bool:
        token = str(payload.get("approval_token") or "")
        if not token:
            return False
        approvals = self._read_approvals()
        record = approvals.pop(token, None)
        self._write_approvals(approvals)
        if not isinstance(record, dict):
            return False
        if record.get("action") != action:
            return False
        if record.get("payload") != expected_payload:
            return False
        if float(record.get("expires_at") or 0) < time.time():
            return False
        return True

    def _read_approvals(self) -> dict[str, Any]:
        try:
            value = json.loads(self._approval_path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return {}
        except Exception:
            return {}
        now = time.time()
        return {
            token: record
            for token, record in value.items()
            if isinstance(record, dict) and float(record.get("expires_at") or 0) >= now
        }

    def _write_approvals(self, value: dict[str, Any]) -> None:
        self._approval_path.parent.mkdir(parents=True, exist_ok=True)
        self._approval_path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key not in {"approved", "approval_token"}}
