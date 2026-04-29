from __future__ import annotations

import json
import platform
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

    def run(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if action == "browser.open_url":
            return self._open_url(str(payload.get("url", "")), approved=bool(payload.get("approved")), dry_run=bool(payload.get("dry_run")))
        if action == "browser.session":
            return {"action": action, "session": self._read_sessions()}
        if action == "computer.screenshot":
            return self._screenshot(approved=bool(payload.get("approved")), dry_run=bool(payload.get("dry_run")))
        if action in {"computer.click", "computer.type", "computer.key", "computer.scroll"}:
            return self._desktop_action(action, payload)
        raise ValueError(f"Unsupported browser/computer action: {action}")

    def _open_url(self, url: str, *, approved: bool, dry_run: bool) -> dict[str, Any]:
        if not url.startswith(("http://", "https://", "file://")):
            raise ValueError("'url' must start with http://, https://, or file://")
        if dry_run:
            return {"action": "browser.open_url", "url": url, "dry_run": True, "requires_approval": False}
        if not approved:
            return {"action": "browser.open_url", "url": url, "requires_approval": True}
        webbrowser.open(url)
        sessions = self._read_sessions()
        sessions["last_url"] = url
        sessions["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._write_sessions(sessions)
        return {"action": "browser.open_url", "url": url, "opened": True}

    def _screenshot(self, *, approved: bool, dry_run: bool) -> dict[str, Any]:
        if dry_run:
            return {"action": "computer.screenshot", "dry_run": True, "requires_approval": False}
        if not approved:
            return {"action": "computer.screenshot", "requires_approval": True}
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
        if not bool(payload.get("approved")):
            return {"action": action, "requires_approval": True, "payload": payload}
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
