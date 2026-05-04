from __future__ import annotations

import json
import platform
import secrets
import subprocess
import time
import webbrowser
import base64
from pathlib import Path
from typing import Any


class BrowserComputerController:
    """Generic browser/computer action controller with approval gates."""

    def __init__(self, artifact_root: Path | None = None) -> None:
        pack_root = Path(__file__).resolve().parents[2]
        self._artifact_root = artifact_root or pack_root / "user_data" / "artifacts" / "computer"
        self._session_path = pack_root / "user_data" / "shared" / "browser_sessions.json"
        self._approval_path = pack_root / "user_data" / "shared" / "browser_computer_approvals.json"

    def run(self, action: str, payload: dict[str, Any] | None = None, *, yolo_mode: bool = False) -> dict[str, Any]:
        payload = payload or {}
        if action == "browser.open_url":
            return self._open_url(str(payload.get("url", "")), payload=payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action == "browser.session":
            return {"action": action, "platform": platform.system(), "capabilities": self._capabilities(), "session": self._read_sessions()}
        if action == "computer.screenshot":
            return self._screenshot(payload=payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action in {"computer.click", "computer.type", "computer.key", "computer.scroll"}:
            return self._desktop_action(action, payload, yolo_mode=yolo_mode)
        raise ValueError(f"Unsupported browser/computer action: {action}")

    def _open_url(self, url: str, *, payload: dict[str, Any], dry_run: bool, yolo_mode: bool) -> dict[str, Any]:
        if not url.startswith(("http://", "https://", "file://")):
            raise ValueError("'url' must start with http://, https://, or file://")
        if dry_run:
            return {"action": "browser.open_url", "url": url, "dry_run": True, "requires_approval": False}
        approved = yolo_mode or self._consume_approval(payload, "browser.open_url", {"url": url})
        if not approved:
            return self._approval_required("browser.open_url", {"url": url})
        webbrowser.open(url)
        sessions = self._read_sessions()
        sessions["last_url"] = url
        sessions["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._write_sessions(sessions)
        return {"action": "browser.open_url", "url": url, "opened": True}

    def _screenshot(self, *, payload: dict[str, Any], dry_run: bool, yolo_mode: bool) -> dict[str, Any]:
        if dry_run:
            return {"action": "computer.screenshot", "dry_run": True, "requires_approval": False}
        approved = yolo_mode or self._consume_approval(payload, "computer.screenshot", {})
        if not approved:
            return self._approval_required("computer.screenshot", {})
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        path = self._artifact_root / f"screenshot-{int(time.time() * 1000)}.png"
        system = platform.system()
        if system == "Darwin":
            subprocess.run(["screencapture", "-x", str(path)], check=True)
        elif system == "Windows":
            self._windows_screenshot(path)
        else:
            return {
                "action": "computer.screenshot",
                "supported": False,
                "platform": system,
                "reason": "Screenshots are supported on macOS and Windows.",
            }
        model_path = self._model_screenshot_copy(path)
        data_url = ""
        try:
            mime_type = "image/jpeg" if model_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            data_url = "data:{};base64,".format(mime_type) + base64.b64encode(model_path.read_bytes()).decode("ascii")
        except Exception:
            data_url = ""
        result = {"action": "computer.screenshot", "path": str(path), "mime_type": "image/png", "platform": system}
        if data_url:
            result["data_url"] = data_url
            result["model_image_path"] = str(model_path)
        return result

    def _model_screenshot_copy(self, path: Path) -> Path:
        preview_path = path.with_name(path.stem + "-model.jpg")
        if platform.system() == "Darwin":
            try:
                subprocess.run(
                    ["sips", "-Z", "640", "-s", "format", "jpeg", str(path), "--out", str(preview_path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if preview_path.exists() and preview_path.stat().st_size > 0:
                    return preview_path
            except Exception:
                pass
        return path

    def _desktop_action(self, action: str, payload: dict[str, Any], *, yolo_mode: bool) -> dict[str, Any]:
        dry_run = bool(payload.get("dry_run"))
        if dry_run:
            return {"action": action, "dry_run": True, "requires_approval": False, "payload": payload}
        approval_payload = self._safe_payload(payload)
        if not (yolo_mode or self._consume_approval(payload, action, approval_payload)):
            return self._approval_required(action, approval_payload)
        system = platform.system()
        if system == "Darwin":
            script = self._apple_script(action, payload)
            subprocess.run(["osascript", "-e", script], check=True)
        elif system == "Windows":
            self._windows_desktop_action(action, payload)
        else:
            return {
                "action": action,
                "supported": False,
                "platform": system,
                "reason": "Desktop actions are supported on macOS and Windows.",
            }
        return {"action": action, "executed": True, "platform": system}

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

    def _windows_screenshot(self, path: Path) -> None:
        escaped = self._ps_single(str(path))
        script = "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "Add-Type -AssemblyName System.Windows.Forms",
                "Add-Type -AssemblyName System.Drawing",
                "$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds",
                "$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height",
                "$graphics = [System.Drawing.Graphics]::FromImage($bitmap)",
                "$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)",
                f"$bitmap.Save('{escaped}', [System.Drawing.Imaging.ImageFormat]::Png)",
                "$graphics.Dispose()",
                "$bitmap.Dispose()",
            ]
        )
        self._run_powershell(script)

    def _windows_desktop_action(self, action: str, payload: dict[str, Any]) -> None:
        prelude = [
            "$ErrorActionPreference = 'Stop'",
            "Add-Type -AssemblyName System.Windows.Forms",
            "Add-Type -AssemblyName System.Drawing",
        ]
        if action == "computer.click":
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
            script = "\n".join(
                prelude
                + [
                    "Add-Type -TypeDefinition @'\nusing System;\nusing System.Runtime.InteropServices;\npublic class RumiMouse {\n  [DllImport(\"user32.dll\")]\n  public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);\n}\n'@",
                    f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})",
                    "[RumiMouse]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)",
                    "[RumiMouse]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)",
                ]
            )
            self._run_powershell(script)
            return
        if action == "computer.type":
            text = self._ps_single(str(payload.get("text", "")))
            self._run_powershell("\n".join(prelude + [f"[System.Windows.Forms.SendKeys]::SendWait('{text}')"]))
            return
        if action == "computer.key":
            key = self._windows_send_key(str(payload.get("key", "ENTER")))
            self._run_powershell("\n".join(prelude + [f"[System.Windows.Forms.SendKeys]::SendWait('{key}')"]))
            return
        if action == "computer.scroll":
            amount = int(payload.get("amount", 1))
            wheel_delta = amount * 120
            script = "\n".join(
                prelude
                + [
                    "Add-Type -TypeDefinition @'\nusing System;\nusing System.Runtime.InteropServices;\npublic class RumiMouse {\n  [DllImport(\"user32.dll\")]\n  public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);\n}\n'@",
                    f"[RumiMouse]::mouse_event(0x0800, 0, 0, [uint32]({wheel_delta}), [UIntPtr]::Zero)",
                ]
            )
            self._run_powershell(script)
            return
        raise ValueError(action)

    @staticmethod
    def _windows_send_key(key: str) -> str:
        normalized = key.strip().lower()
        key_map = {
            "enter": "{ENTER}",
            "return": "{ENTER}",
            "escape": "{ESC}",
            "esc": "{ESC}",
            "tab": "{TAB}",
            "backspace": "{BACKSPACE}",
            "delete": "{DELETE}",
            "up": "{UP}",
            "down": "{DOWN}",
            "left": "{LEFT}",
            "right": "{RIGHT}",
        }
        return key_map.get(normalized, key)

    @staticmethod
    def _ps_single(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def _run_powershell(script: str) -> None:
        executable = "powershell"
        try:
            subprocess.run([executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=True)
        except FileNotFoundError:
            subprocess.run(["pwsh", "-NoProfile", "-Command", script], check=True)

    @staticmethod
    def _capabilities() -> dict[str, bool]:
        system = platform.system()
        return {
            "browser_open_url": True,
            "screenshot": system in {"Darwin", "Windows"},
            "desktop_actions": system in {"Darwin", "Windows"},
        }

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
