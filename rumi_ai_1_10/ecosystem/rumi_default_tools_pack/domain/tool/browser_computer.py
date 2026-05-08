from __future__ import annotations

import json
import os
import platform
import re
import secrets
import shutil
import struct
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
        self._browser_root = pack_root / "user_data" / "shared" / "browser"
        self._profile_root = self._browser_root / "profiles"

    def run(self, action: str, payload: dict[str, Any] | None = None, *, yolo_mode: bool = False) -> dict[str, Any]:
        payload = payload or {}
        if action == "browser.open_url":
            return self._open_url(str(payload.get("url", "")), payload=payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action == "browser.session":
            return {"action": action, "platform": platform.system(), "capabilities": self._capabilities(), "session": self._read_sessions()}
        if action == "browser.profiles.list":
            return {"action": action, "profiles": self._list_profiles(), "active_profile_id": self._active_profile_id()}
        if action == "browser.profile.create":
            return self._create_profile(payload)
        if action == "browser.profile.set_active":
            return self._set_active_profile(payload)
        if action == "browser.profile.delete":
            return self._delete_profile(payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action == "browser.profile.clear_cache":
            return self._clear_cache(payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action == "browser.profile.clear_cookies":
            return self._clear_cookies(payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action == "browser.cookies.list":
            return self._list_cookies(payload)
        if action == "browser.cookies.import":
            return self._import_cookies(payload)
        if action == "browser.cookies.delete":
            return self._delete_cookies(payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action in {"computer.context", "computer.app_context", "computer.state"}:
            return self._context(payload)
        if action in {"computer.windows", "computer.list_windows"}:
            return {"action": "computer.windows", "platform": platform.system(), "windows": self._list_windows()}
        if action == "computer.select_window":
            return self._select_window(payload)
        if action == "computer.screenshot":
            return self._screenshot(payload=payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action in {"computer.move", "computer.click", "computer.type", "computer.key", "computer.scroll"}:
            return self._desktop_action(action, payload, yolo_mode=yolo_mode)
        raise ValueError(f"Unsupported browser/computer action: {action}")

    def _open_url(self, url: str, *, payload: dict[str, Any], dry_run: bool, yolo_mode: bool) -> dict[str, Any]:
        if not url.startswith(("http://", "https://", "file://")):
            raise ValueError("'url' must start with http://, https://, or file://")
        profile_id = self._profile_id(payload.get("profile_id") or payload.get("session_id") or self._active_profile_id())
        persistent = payload.get("persistent", True) is not False
        launch_plan = self._browser_launch_plan(url, profile_id, persistent=persistent)
        if dry_run:
            return {
                "action": "browser.open_url",
                "url": url,
                "profile_id": profile_id,
                "persistent": persistent,
                "dry_run": True,
                "requires_approval": False,
                "launch": launch_plan,
            }
        approval_payload = {"url": url, "profile_id": profile_id, "persistent": persistent}
        approved = yolo_mode or self._consume_approval(payload, "browser.open_url", approval_payload)
        if not approved:
            return self._approval_required("browser.open_url", approval_payload)
        self._ensure_profile(profile_id)
        opened_with_managed_profile = False
        if persistent and launch_plan.get("command"):
            command = [str(part) for part in launch_plan["command"]]
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opened_with_managed_profile = True
        else:
            chrome_target = self._open_in_existing_browser(url)
        sessions = self._read_sessions()
        sessions["last_url"] = url
        sessions["active_profile_id"] = profile_id
        sessions["last_opened_with_managed_profile"] = opened_with_managed_profile
        sessions["last_opened_background"] = not opened_with_managed_profile
        if not opened_with_managed_profile and chrome_target:
            sessions["chrome_target"] = chrome_target
        sessions["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._write_sessions(sessions)
        return {
            "action": "browser.open_url",
            "url": url,
            "opened": True,
            "profile_id": profile_id,
            "persistent": persistent,
            "managed_profile": opened_with_managed_profile,
            "launch": launch_plan,
            **({"chrome_target": chrome_target} if not opened_with_managed_profile and chrome_target else {}),
        }

    @staticmethod
    def _open_in_existing_browser(url: str) -> dict[str, Any] | None:
        if platform.system() == "Darwin":
            try:
                script = """
tell application "System Events"
  set previousFrontApp to name of first application process whose frontmost is true
end tell
tell application "Google Chrome"
  set tabChar to ASCII character 9
  if (count of windows) is 0 then
    make new window
  end if
  set targetWindow to window 1
  set targetWindowIndex to 1
  set newTab to make new tab at end of tabs of targetWindow with properties {URL:%s}
  set active tab index of targetWindow to (count of tabs of targetWindow)
  set targetTabIndex to active tab index of targetWindow
end tell
try
  tell application "System Events" to set frontmost of first application process whose name is previousFrontApp to true
end try
return "window_index=" & targetWindowIndex & tabChar & "tab_index=" & targetTabIndex
""" % json.dumps(url)
                completed = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
                target = {"app": "Google Chrome", "url": url}
                for part in (completed.stdout or "").strip().split("\t"):
                    key, _, value = part.partition("=")
                    if key in {"window_index", "tab_index"}:
                        try:
                            target[key] = int(value)
                        except ValueError:
                            pass
                return target
            except Exception:
                pass
        webbrowser.open(url)
        return {"url": url}

    def _create_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = self._profile_id(payload.get("profile_id") or payload.get("name") or f"profile-{int(time.time())}")
        label = str(payload.get("label") or payload.get("name") or profile_id)
        profile = self._ensure_profile(profile_id, label=label)
        if payload.get("set_active", True) is not False:
            sessions = self._read_sessions()
            sessions["active_profile_id"] = profile_id
            sessions["updated_at"] = self._now_iso()
            self._write_sessions(sessions)
        return {"action": "browser.profile.create", "profile": self._profile_summary(profile_id, profile), "active_profile_id": self._active_profile_id()}

    def _set_active_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = self._profile_id(payload.get("profile_id") or payload.get("session_id"))
        self._ensure_profile(profile_id)
        sessions = self._read_sessions()
        sessions["active_profile_id"] = profile_id
        sessions["updated_at"] = self._now_iso()
        self._write_sessions(sessions)
        return {"action": "browser.profile.set_active", "active_profile_id": profile_id}

    def _delete_profile(self, payload: dict[str, Any], *, dry_run: bool, yolo_mode: bool) -> dict[str, Any]:
        profile_id = self._profile_id(payload.get("profile_id") or payload.get("session_id"))
        if profile_id == "default":
            raise ValueError("The default browser profile cannot be deleted.")
        profile_path = self._profile_path(profile_id)
        approval_payload = {"profile_id": profile_id}
        if dry_run:
            return {
                "action": "browser.profile.delete",
                "profile_id": profile_id,
                "dry_run": True,
                "requires_approval": False,
                "exists": profile_path.exists(),
            }
        if not (yolo_mode or self._consume_approval(payload, "browser.profile.delete", approval_payload)):
            return self._approval_required("browser.profile.delete", approval_payload)
        shutil.rmtree(profile_path, ignore_errors=True)
        sessions = self._read_sessions()
        profiles = sessions.get("profiles") if isinstance(sessions.get("profiles"), dict) else {}
        profiles.pop(profile_id, None)
        sessions["profiles"] = profiles
        if sessions.get("active_profile_id") == profile_id:
            sessions["active_profile_id"] = "default"
        sessions["updated_at"] = self._now_iso()
        self._write_sessions(sessions)
        return {"action": "browser.profile.delete", "profile_id": profile_id, "deleted": True}

    def _clear_cache(self, payload: dict[str, Any], *, dry_run: bool, yolo_mode: bool) -> dict[str, Any]:
        profile_id = self._profile_id(payload.get("profile_id") or payload.get("session_id") or self._active_profile_id())
        self._ensure_profile(profile_id)
        candidates = self._cache_paths(profile_id)
        existing = [path for path in candidates if path.exists()]
        approval_payload = {"profile_id": profile_id}
        if dry_run:
            return {
                "action": "browser.profile.clear_cache",
                "profile_id": profile_id,
                "dry_run": True,
                "requires_approval": False,
                "paths": [str(path) for path in existing],
                "size_bytes": sum(self._path_size(path) for path in existing),
            }
        if not (yolo_mode or self._consume_approval(payload, "browser.profile.clear_cache", approval_payload)):
            return self._approval_required("browser.profile.clear_cache", approval_payload)
        removed = [str(path) for path in existing if self._remove_path(path)]
        return {"action": "browser.profile.clear_cache", "profile_id": profile_id, "removed": removed}

    def _clear_cookies(self, payload: dict[str, Any], *, dry_run: bool, yolo_mode: bool) -> dict[str, Any]:
        profile_id = self._profile_id(payload.get("profile_id") or payload.get("session_id") or self._active_profile_id())
        self._ensure_profile(profile_id)
        include_managed = payload.get("include_managed", True) is not False
        candidates = self._browser_cookie_paths(profile_id)
        if include_managed:
            candidates.append(self._cookie_jar_path(profile_id))
        existing = [path for path in candidates if path.exists()]
        approval_payload = {"profile_id": profile_id, "include_managed": include_managed}
        if dry_run:
            return {
                "action": "browser.profile.clear_cookies",
                "profile_id": profile_id,
                "dry_run": True,
                "requires_approval": False,
                "paths": [str(path) for path in existing],
            }
        if not (yolo_mode or self._consume_approval(payload, "browser.profile.clear_cookies", approval_payload)):
            return self._approval_required("browser.profile.clear_cookies", approval_payload)
        removed = [str(path) for path in existing if self._remove_path(path)]
        return {"action": "browser.profile.clear_cookies", "profile_id": profile_id, "removed": removed}

    def _list_cookies(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = self._profile_id(payload.get("profile_id") or payload.get("session_id") or self._active_profile_id())
        jar = self._read_cookie_jar(profile_id)
        include_values = bool(payload.get("include_values"))
        cookies = [self._cookie_public_view(cookie, include_values=include_values) for cookie in jar.get("cookies", [])]
        return {"action": "browser.cookies.list", "profile_id": profile_id, "cookies": cookies, "count": len(cookies)}

    def _import_cookies(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = self._profile_id(payload.get("profile_id") or payload.get("session_id") or self._active_profile_id())
        cookies = payload.get("cookies")
        if not isinstance(cookies, list):
            raise ValueError("'cookies' must be a list")
        normalized = [self._normalize_cookie(cookie) for cookie in cookies if isinstance(cookie, dict)]
        replace = bool(payload.get("replace"))
        current = [] if replace else list(self._read_cookie_jar(profile_id).get("cookies", []))
        merged = self._merge_cookies(current, normalized)
        self._write_cookie_jar(profile_id, {"version": 1, "cookies": merged, "updated_at": self._now_iso()})
        self._ensure_profile(profile_id)
        return {"action": "browser.cookies.import", "profile_id": profile_id, "imported": len(normalized), "count": len(merged)}

    def _delete_cookies(self, payload: dict[str, Any], *, dry_run: bool, yolo_mode: bool) -> dict[str, Any]:
        profile_id = self._profile_id(payload.get("profile_id") or payload.get("session_id") or self._active_profile_id())
        name = str(payload.get("name") or "")
        domain = str(payload.get("domain") or "")
        path = str(payload.get("path") or "")
        approval_payload = {"profile_id": profile_id, "name": name, "domain": domain, "path": path}
        jar = self._read_cookie_jar(profile_id)
        cookies = list(jar.get("cookies", []))
        matches = [cookie for cookie in cookies if self._cookie_matches(cookie, name=name, domain=domain, path=path)]
        if dry_run:
            return {
                "action": "browser.cookies.delete",
                "profile_id": profile_id,
                "dry_run": True,
                "requires_approval": False,
                "matches": len(matches),
            }
        if not (yolo_mode or self._consume_approval(payload, "browser.cookies.delete", approval_payload)):
            return self._approval_required("browser.cookies.delete", approval_payload)
        remaining = [cookie for cookie in cookies if not self._cookie_matches(cookie, name=name, domain=domain, path=path)]
        self._write_cookie_jar(profile_id, {"version": 1, "cookies": remaining, "updated_at": self._now_iso()})
        return {"action": "browser.cookies.delete", "profile_id": profile_id, "deleted": len(cookies) - len(remaining), "count": len(remaining)}

    def _screenshot(self, *, payload: dict[str, Any], dry_run: bool, yolo_mode: bool) -> dict[str, Any]:
        if dry_run:
            return {
                "action": "computer.screenshot",
                "dry_run": True,
                "requires_approval": False,
                "target_window": self._capture_target(payload),
            }
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        path = self._artifact_root / f"screenshot-{int(time.time() * 1000)}.png"
        capture = self._capture_screenshot(path, payload)
        system = capture.get("platform", platform.system())
        if not capture.get("supported", True):
            result = {
                "action": "computer.screenshot",
                "supported": False,
                "platform": system,
                "reason": capture.get("reason") or "Screenshots are supported on macOS and Windows.",
            }
            for key in ("target_filter", "chrome_target", "recovery", "background_target_only"):
                if capture.get(key) is not None:
                    result[key] = capture.get(key)
            return result
        model_path = self._model_screenshot_copy(path)
        data_url = self._image_data_url(model_path)
        result = self._screenshot_result(path, model_path, system, capture_target=capture.get("target_window"))
        if data_url:
            result["data_url"] = data_url
            result["model_image_path"] = str(model_path)
        return result

    def _screenshot_result(
        self,
        path: Path,
        model_path: Path,
        system: str,
        *,
        capture_target: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"action": "computer.screenshot", "path": str(path), "mime_type": "image/png", "platform": system}
        image_size = self._image_size(path)
        model_image_size = self._image_size(model_path)
        if capture_target:
            result["target_window"] = capture_target
        if image_size:
            width, height = image_size
            result["image_size"] = {"width": width, "height": height}
            result["coordinate_system"] = {
                "origin": "top_left",
                "unit": "px",
                "space": "screenshot_image",
                "x_range": [0, max(width - 1, 0)],
                "y_range": [0, max(height - 1, 0)],
            }
        try:
            action_coordinate_system = self._action_coordinate_system(system, image_size, capture_target=capture_target)
        except TypeError:
            action_coordinate_system = self._action_coordinate_system(system, image_size)
        if action_coordinate_system:
            result["action_coordinate_system"] = action_coordinate_system
        if model_image_size:
            model_width, model_height = model_image_size
            result["model_image_size"] = {"width": model_width, "height": model_height}
        if image_size and model_image_size and model_image_size[0] and model_image_size[1]:
            result["model_to_screen_scale"] = {
                "x": image_size[0] / model_image_size[0],
                "y": image_size[1] / model_image_size[1],
            }
        if action_coordinate_system and model_image_size and model_image_size[0] and model_image_size[1]:
            action_width = action_coordinate_system.get("width")
            action_height = action_coordinate_system.get("height")
            if action_width and action_height:
                result["model_to_action_scale"] = {
                    "x": action_width / model_image_size[0],
                    "y": action_height / model_image_size[1],
                }
        if action_coordinate_system and image_size and image_size[0] and image_size[1]:
            action_width = action_coordinate_system.get("width")
            action_height = action_coordinate_system.get("height")
            if action_width and action_height:
                result["screenshot_to_action_scale"] = {
                    "x": action_width / image_size[0],
                    "y": action_height / image_size[1],
                }
        cursor = self._cursor_position()
        if cursor:
            result["cursor"] = cursor
        context = self._context({"include_windows": False})
        if context.get("ai_cursor"):
            result["ai_cursor"] = context.get("ai_cursor")
        if context.get("active_window"):
            result["active_window"] = context.get("active_window")
        if context.get("selected_window"):
            result["selected_window"] = context.get("selected_window")
        result["cursor_move_contract"] = {
            "tool": "browser_use",
            "action": "move",
            "screen_coordinates": True,
            "coordinate_source": "screenshot",
            "notes": "Call move with action_coordinate_system coordinates. If a point is estimated on model_image_size, multiply by model_to_action_scale before calling move.",
        }
        return result

    def _context(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        state = self._computer_state()
        sessions = self._read_sessions()
        system = platform.system()
        chrome_tabs = self._chrome_tabs() if system == "Darwin" else []
        selected_window = state.get("target_window") if isinstance(state.get("target_window"), dict) else None
        if selected_window and not self._is_usable_target_window(selected_window):
            self._clear_target_window()
            selected_window = None
        result: dict[str, Any] = {
            "action": "computer.context",
            "platform": system,
            "active_window": self._active_window(),
            "selected_window": selected_window,
            "ai_cursor": state.get("ai_cursor") if isinstance(state.get("ai_cursor"), dict) else None,
            "cursor": self._cursor_position(),
            "browser_session": {
                "last_url": sessions.get("last_url"),
                "last_opened_background": bool(sessions.get("last_opened_background")),
                "last_opened_with_managed_profile": bool(sessions.get("last_opened_with_managed_profile")),
                "chrome_target": sessions.get("chrome_target") if isinstance(sessions.get("chrome_target"), dict) else None,
            },
            "chrome_tabs": chrome_tabs,
            "chrome_background_control": self._chrome_background_control(chrome_tabs) if system == "Darwin" else None,
            "notes": [
                "Use computer.screenshot with app/title, or computer.select_window with app/title and focus=false, before window-scoped screenshots.",
                "computer.move and computer.click use a virtual AI cursor unless physical=true is explicitly provided.",
                "If Google Chrome tabs are listed but no Chrome window appears in windows, Chrome is open outside the visible app-window context; target it by chrome_target/url_contains for background-capable actions.",
                "chrome_background_control only describes Chrome DOM entry through Apple Events; screenshots, windows, and the virtual AI cursor are still normal computer-use capabilities.",
                "For text/key entry, prefer driver=auto: the harness can try Chrome DOM background entry first, then fall back to foreground input when allow_foreground_fallback=true.",
                "Use background=true without allow_foreground_fallback only when the user forbids foreground focus; if that actual entry returns recovery.kind=chrome_setting, stop and report the blocker.",
            ],
        }
        if payload.get("include_windows", True) is not False:
            result["windows"] = self._list_windows()
        return result

    @staticmethod
    def _image_data_url(path: Path) -> str:
        try:
            mime_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            return "data:{};base64,".format(mime_type) + base64.b64encode(path.read_bytes()).decode("ascii")
        except Exception:
            return ""

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

    @staticmethod
    def _image_size(path: Path) -> tuple[int, int] | None:
        try:
            data = path.read_bytes()
        except Exception:
            return None
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            try:
                width, height = struct.unpack(">II", data[16:24])
                return int(width), int(height)
            except Exception:
                return None
        if data.startswith(b"\xff\xd8"):
            index = 2
            while index + 9 < len(data):
                if data[index] != 0xFF:
                    index += 1
                    continue
                marker = data[index + 1]
                index += 2
                if marker in {0xD8, 0xD9}:
                    continue
                if index + 2 > len(data):
                    return None
                length = int.from_bytes(data[index : index + 2], "big")
                if length < 2 or index + length > len(data):
                    return None
                if 0xC0 <= marker <= 0xCF and marker not in {0xC4, 0xC8, 0xCC} and length >= 7:
                    height = int.from_bytes(data[index + 3 : index + 5], "big")
                    width = int.from_bytes(data[index + 5 : index + 7], "big")
                    return int(width), int(height)
                index += length
        return None

    @staticmethod
    def _cursor_position() -> dict[str, Any] | None:
        system = platform.system()
        try:
            if system == "Darwin":
                code = (
                    "import json, Quartz\n"
                    "event = Quartz.CGEventCreate(None)\n"
                    "loc = Quartz.CGEventGetLocation(event)\n"
                    "print(json.dumps({'x': int(round(loc.x)), 'y': int(round(loc.y)), 'origin': 'top_left'}))"
                )
                completed = subprocess.run(["python3", "-c", code], check=True, capture_output=True, text=True)
                value = json.loads(completed.stdout or "{}")
                if "x" in value and "y" in value:
                    return value
            if system == "Windows":
                script = "\n".join(
                    [
                        "Add-Type -AssemblyName System.Windows.Forms",
                        "$p = [System.Windows.Forms.Cursor]::Position",
                        "ConvertTo-Json @{ x = [int]$p.X; y = [int]$p.Y; origin = 'top_left' } -Compress",
                    ]
                )
                executable = "powershell" if shutil.which("powershell") else "pwsh"
                completed = subprocess.run([executable, "-NoProfile", "-Command", script], check=True, capture_output=True, text=True)
                value = json.loads(completed.stdout or "{}")
                if "x" in value and "y" in value:
                    return value
        except Exception:
            return None
        return None

    @staticmethod
    def _action_coordinate_system(
        system: str,
        image_size: tuple[int, int] | None,
        *,
        capture_target: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if capture_target and capture_target.get("width") and capture_target.get("height"):
            x = int(capture_target.get("x", 0))
            y = int(capture_target.get("y", 0))
            width = int(capture_target.get("width", 0))
            height = int(capture_target.get("height", 0))
            return {
                "origin": "top_left",
                "unit": "display_coordinate",
                "screen": "selected_window",
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "x_range": [x, x + max(width - 1, 0)],
                "y_range": [y, y + max(height - 1, 0)],
            }
        if system == "Darwin":
            try:
                code = (
                    "import json, Quartz\n"
                    "display = Quartz.CGMainDisplayID()\n"
                    "bounds = Quartz.CGDisplayBounds(display)\n"
                    "payload = {\n"
                    "  'origin': 'top_left',\n"
                    "  'unit': 'display_coordinate',\n"
                    "  'screen': 'primary',\n"
                    "  'x': int(round(bounds.origin.x)),\n"
                    "  'y': int(round(bounds.origin.y)),\n"
                    "  'width': int(round(bounds.size.width)),\n"
                    "  'height': int(round(bounds.size.height)),\n"
                    "}\n"
                    "payload['x_range'] = [payload['x'], payload['x'] + max(payload['width'] - 1, 0)]\n"
                    "payload['y_range'] = [payload['y'], payload['y'] + max(payload['height'] - 1, 0)]\n"
                    "print(json.dumps(payload))"
                )
                completed = subprocess.run(["python3", "-c", code], check=True, capture_output=True, text=True)
                value = json.loads(completed.stdout or "{}")
                if value.get("width") and value.get("height"):
                    return value
            except Exception:
                pass
        if system == "Windows" and image_size:
            width, height = image_size
            return {
                "origin": "top_left",
                "unit": "px",
                "screen": "primary",
                "x": 0,
                "y": 0,
                "width": width,
                "height": height,
                "x_range": [0, max(width - 1, 0)],
                "y_range": [0, max(height - 1, 0)],
            }
        if image_size:
            width, height = image_size
            return {
                "origin": "top_left",
                "unit": "px",
                "screen": "captured",
                "x": 0,
                "y": 0,
                "width": width,
                "height": height,
                "x_range": [0, max(width - 1, 0)],
                "y_range": [0, max(height - 1, 0)],
            }
        return None

    def _desktop_action(self, action: str, payload: dict[str, Any], *, yolo_mode: bool) -> dict[str, Any]:
        dry_run = bool(payload.get("dry_run"))
        if dry_run:
            return {"action": action, "dry_run": True, "requires_approval": False, "payload": payload}
        approval_payload = self._safe_payload(payload)
        if not (yolo_mode or self._consume_approval(payload, action, approval_payload)):
            return self._approval_required(action, approval_payload)
        system = platform.system()
        action_payload = dict(payload)
        click_marker = None
        if action in {"computer.move", "computer.click"}:
            action_payload, click_marker = self._resolve_action_point(payload, infer_window=action == "computer.click")
        if action in {"computer.move", "computer.click"} and payload.get("physical") is not True:
            self._set_ai_cursor(action_payload)
            result: dict[str, Any] = {"action": action, "executed": True, "platform": system, "virtual_cursor": True}
            result["target"] = {"x": int(action_payload.get("x", 0)), "y": int(action_payload.get("y", 0))}
            if click_marker:
                result["marker"] = click_marker
            if action == "computer.click" and payload.get("include_screenshot", True) is not False:
                screenshot = self._capture_action_result_screenshot(action_payload, click_marker)
                result.update(screenshot)
            return result
        background_chrome = system == "Darwin" and self._should_type_in_chrome_background(action_payload)
        background_failure: dict[str, Any] | None = None
        if action == "computer.type" and background_chrome:
            chrome_target = self._chrome_background_target(action_payload)
            if self._darwin_type_in_chrome_background(str(action_payload.get("text") or ""), action_payload):
                return {
                    "action": action,
                    "executed": True,
                    "platform": system,
                    "background": True,
                    "driver": "chrome_background_dom",
                    "driver_sequence": ["chrome_background_dom"],
                    "target_app": "Google Chrome",
                    "chrome_target": chrome_target,
                }
            reason = self._chrome_background_failure_reason("Chrome background text entry failed.")
            background_failure = {
                "action": action,
                "executed": False,
                "is_error": True,
                "platform": system,
                "background": True,
                "target_app": "Google Chrome",
                "chrome_target": chrome_target,
                "reason": reason,
                "recovery": {
                    "kind": "chrome_setting",
                    "setting": "Allow JavaScript from Apple Events",
                    "path": "View > Developer > Allow JavaScript from Apple Events",
                    "note": "Without this Chrome setting, background DOM entry into an existing user Chrome tab is blocked by Chrome.",
                },
            }
            if not self._allow_foreground_fallback(action_payload):
                return background_failure
            action_payload["background"] = False
        if action == "computer.key" and background_chrome:
            key = str(action_payload.get("key") or "").strip().lower()
            modifiers = action_payload.get("modifiers")
            if not isinstance(modifiers, list):
                modifier = action_payload.get("modifier")
                modifiers = [modifier] if modifier else []
            chrome_target = self._chrome_background_target(action_payload)
            if self._darwin_key_in_chrome_background(key, modifiers, action_payload):
                return {
                    "action": action,
                    "executed": True,
                    "platform": system,
                    "background": True,
                    "driver": "chrome_background_dom",
                    "driver_sequence": ["chrome_background_dom"],
                    "target_app": "Google Chrome",
                    "chrome_target": chrome_target,
                }
            reason = self._chrome_background_failure_reason("Chrome background key entry failed or unsupported.")
            background_failure = {
                "action": action,
                "executed": False,
                "is_error": True,
                "platform": system,
                "background": True,
                "target_app": "Google Chrome",
                "chrome_target": chrome_target,
                "reason": reason,
                "recovery": {
                    "kind": "chrome_setting",
                    "setting": "Allow JavaScript from Apple Events",
                    "path": "View > Developer > Allow JavaScript from Apple Events",
                    "note": "Without this Chrome setting, background key entry into an existing user Chrome tab is blocked by Chrome.",
                },
            }
            if not self._allow_foreground_fallback(action_payload):
                return background_failure
            action_payload["background"] = False
        if action in {"computer.type", "computer.key", "computer.scroll"}:
            self._focus_action_target(action_payload)
        if system == "Darwin" and action == "computer.move":
            self._darwin_move_cursor(action_payload)
        elif system == "Darwin" and action == "computer.click":
            self._darwin_click(action_payload)
        elif system == "Darwin":
            script = self._apple_script(action, action_payload)
            subprocess.run(["osascript", "-e", script], check=True)
        elif system == "Windows":
            self._windows_desktop_action(action, action_payload)
        else:
            return {
                "action": action,
                "supported": False,
                "platform": system,
                "reason": "Desktop actions are supported on macOS and Windows.",
            }
        result: dict[str, Any] = {"action": action, "executed": True, "platform": system}
        if action in {"computer.type", "computer.key", "computer.scroll"}:
            result["driver"] = "foreground_input"
        if action in {"computer.move", "computer.click"}:
            result["target"] = {"x": int(action_payload.get("x", 0)), "y": int(action_payload.get("y", 0))}
            if click_marker:
                result["marker"] = click_marker
        if action == "computer.scroll":
            result["amount"] = int(action_payload.get("amount", 1))
        if action == "computer.click" and payload.get("include_screenshot", True) is not False:
            screenshot = self._capture_action_result_screenshot(action_payload, click_marker)
            result.update(screenshot)
        if background_failure:
            result["background_attempted"] = True
            result["foreground_fallback"] = True
            result["driver_sequence"] = ["chrome_background_dom", "foreground_input"]
            result["background_failure"] = {
                "reason": background_failure.get("reason"),
                "recovery": background_failure.get("recovery"),
                "chrome_target": background_failure.get("chrome_target"),
            }
        return result

    def _should_type_in_chrome_background(self, payload: dict[str, Any]) -> bool:
        if not self._payload_targets_chrome(payload):
            return False
        if payload.get("background") is True:
            return True
        mode = str(payload.get("mode") or payload.get("method") or "").strip().lower()
        return mode in {"background", "chrome_background", "chrome_background_dom", "background_dom"}

    def _payload_targets_chrome(self, payload: dict[str, Any]) -> bool:
        app = str(payload.get("app") or payload.get("application") or "").strip().lower()
        if app:
            return "chrome" in app
        title = str(payload.get("title") or payload.get("title_contains") or "").strip().lower()
        url = str(payload.get("url") or payload.get("url_contains") or "").strip().lower()
        if "chatgpt" in title or "chrome" in title or "chatgpt" in url or "chrome://" in url:
            return True
        if payload.get("window_index") is not None or payload.get("tab_index") is not None:
            return True
        selected_window = self._computer_state().get("target_window")
        if isinstance(selected_window, dict) and "chrome" in str(selected_window.get("app") or "").lower():
            return True
        sessions = self._read_sessions()
        if isinstance(sessions.get("chrome_target"), dict):
            return True
        last_url = str(sessions.get("last_url") or "").lower()
        return "chatgpt.com" in last_url or "chrome" in last_url

    @staticmethod
    def _allow_foreground_fallback(payload: dict[str, Any]) -> bool:
        if payload.get("allow_foreground_fallback") is False or payload.get("foreground_fallback") is False:
            return False
        if payload.get("physical") is False:
            return False
        if (
            payload.get("allow_foreground_fallback") is True
            or payload.get("foreground_fallback") is True
            or payload.get("allow_user_input_overlap") is True
            or payload.get("input_overlap_ok") is True
            or payload.get("physical") is True
        ):
            return True
        mode = str(payload.get("mode") or payload.get("method") or payload.get("driver") or "").strip().lower()
        return mode in {
            "auto",
            "auto_fallback",
            "foreground",
            "foreground_input",
            "foreground_fallback",
            "physical",
            "overlap_ok",
        }

    def _focus_action_target(self, payload: dict[str, Any]) -> bool:
        if payload.get("focus") is False and not self._allow_foreground_fallback(payload):
            return False
        app = str(payload.get("app") or payload.get("application") or "").strip().lower()
        title = str(payload.get("title") or "").strip().lower()
        selected = self._capture_target(payload)
        if selected and self._window_matches_filter(selected, app=app, title=title):
            self._focus_window(selected)
            return True
        if app or title:
            for item in self._list_windows():
                window = self._normalize_window_record(item)
                if window and self._is_usable_target_window(window) and self._window_matches_filter(window, app=app, title=title):
                    self._focus_window(window)
                    return True
        if platform.system() == "Darwin" and (("chrome" in app) or self._chrome_background_target(payload)):
            return self._activate_chrome_target(payload)
        return False

    @staticmethod
    def _window_matches_filter(window: dict[str, Any], *, app: str = "", title: str = "") -> bool:
        item_app = str(window.get("app") or "").lower()
        item_title = str(window.get("title") or "").lower()
        if app and app not in item_app:
            return False
        if title and title not in item_title:
            return False
        return True

    def _chrome_background_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        sessions = self._read_sessions()
        target: dict[str, Any] = {}
        session_target = sessions.get("chrome_target")
        if isinstance(session_target, dict):
            target.update(session_target)
        for key in ("window_index", "tab_index", "url_contains", "title_contains"):
            if payload.get(key) is not None:
                target[key] = payload.get(key)
        selected_window = self._computer_state().get("target_window")
        if isinstance(selected_window, dict):
            app = str(selected_window.get("app") or "").lower()
            title = str(selected_window.get("title") or "").strip()
            if "chrome" in app and title:
                target.setdefault("title_contains", title)
                target["selected_window"] = selected_window
        last_url = str(sessions.get("last_url") or "")
        if "url_contains" not in target and "chatgpt" in last_url.lower():
            target["url_contains"] = "chatgpt.com"
        elif "url_contains" not in target and last_url:
            target["url_contains"] = last_url
        return target

    @staticmethod
    def _chrome_tabs() -> list[dict[str, Any]]:
        if platform.system() != "Darwin":
            return []
        script = r'''
tell application "Google Chrome"
  set tabChar to ASCII character 9
  set output to ""
  repeat with wi from 1 to count of windows
    set candidateWindow to window wi
    repeat with ti from 1 to count of tabs of candidateWindow
      set candidateTab to tab ti of candidateWindow
      set tabTitle to ""
      set tabUrl to ""
      try
        set tabTitle to title of candidateTab
        set tabUrl to URL of candidateTab
      end try
      set isActive to ((active tab index of candidateWindow) is ti)
      set output to output & wi & tabChar & ti & tabChar & isActive & tabChar & tabTitle & tabChar & tabUrl & linefeed
    end repeat
  end repeat
  return output
end tell
'''
        try:
            completed = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        except Exception:
            return []
        tabs: list[dict[str, Any]] = []
        for line in (completed.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            try:
                window_index = int(parts[0])
                tab_index = int(parts[1])
            except Exception:
                continue
            tabs.append(
                {
                    "app": "Google Chrome",
                    "window_index": window_index,
                    "tab_index": tab_index,
                    "active": parts[2].strip().lower() == "true",
                    "title": parts[3],
                    "url": parts[4],
                }
            )
        return tabs

    def _select_chrome_tab(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        title = str(payload.get("title") or "").strip().lower()
        url_contains = str(payload.get("url_contains") or payload.get("url") or "").strip().lower()
        tabs = self._chrome_tabs()
        selected = None
        for tab in tabs:
            tab_title = str(tab.get("title") or "").lower()
            tab_url = str(tab.get("url") or "").lower()
            if title and title not in tab_title:
                continue
            if url_contains and url_contains not in tab_url:
                continue
            selected = tab
            break
        if selected is None and not title and not url_contains:
            selected = next((tab for tab in tabs if tab.get("active")), None) or (tabs[0] if tabs else None)
        if selected is None:
            return None
        chrome_target = {
            "app": "Google Chrome",
            "window_index": selected.get("window_index"),
            "tab_index": selected.get("tab_index"),
            "title_contains": selected.get("title"),
            "url": selected.get("url"),
            "url_contains": "chatgpt.com" if "chatgpt.com" in str(selected.get("url") or "").lower() else selected.get("url"),
        }
        sessions = self._read_sessions()
        sessions["chrome_target"] = chrome_target
        sessions["last_opened_background"] = True
        if selected.get("url"):
            sessions["last_url"] = selected.get("url")
        sessions["updated_at"] = self._now_iso()
        self._write_sessions(sessions)
        return chrome_target

    def _darwin_execute_chrome_background_js(self, js: str, payload: dict[str, Any]) -> str:
        target = self._chrome_background_target(payload)
        try:
            window_index = int(target.get("window_index") or 0)
        except Exception:
            window_index = 0
        try:
            tab_index = int(target.get("tab_index") or 0)
        except Exception:
            tab_index = 0
        title_contains = str(target.get("title_contains") or "")
        url_contains = str(target.get("url_contains") or "")
        script = """
tell application "Google Chrome"
  if (count of windows) is 0 then return "no_window"
  set jsCode to %s
  set targetWindowIndex to %d
  set targetTabIndex to %d
  set titleNeedle to %s
  set urlNeedle to %s
  try
    if targetWindowIndex > 0 and targetWindowIndex <= (count of windows) then
      set candidateWindow to window targetWindowIndex
      if targetTabIndex > 0 and targetTabIndex <= (count of tabs of candidateWindow) then
        return execute tab targetTabIndex of candidateWindow javascript jsCode
      end if
    end if
  end try
  if titleNeedle is not "" or urlNeedle is not "" then
    repeat with wi from 1 to count of windows
      set candidateWindow to window wi
      repeat with ti from 1 to count of tabs of candidateWindow
        set candidateTab to tab ti of candidateWindow
        set tabTitle to ""
        set tabUrl to ""
        try
          set tabTitle to title of candidateTab
          set tabUrl to URL of candidateTab
        end try
        if (titleNeedle is not "" and tabTitle contains titleNeedle) or (urlNeedle is not "" and tabUrl contains urlNeedle) then
          return execute candidateTab javascript jsCode
        end if
      end repeat
    end repeat
  end if
  return execute active tab of window 1 javascript jsCode
end tell
""" % (json.dumps(js), window_index, tab_index, json.dumps(title_contains), json.dumps(url_contains))
        try:
            completed = subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            self._last_background_error = (exc.stderr or exc.stdout or str(exc)).strip()
            raise
        return completed.stdout or ""

    def _activate_chrome_target(self, payload: dict[str, Any]) -> bool:
        target = self._chrome_background_target(payload)
        try:
            window_index = int(target.get("window_index") or 0)
        except Exception:
            window_index = 0
        try:
            tab_index = int(target.get("tab_index") or 0)
        except Exception:
            tab_index = 0
        title_contains = str(target.get("title_contains") or "")
        url_contains = str(target.get("url_contains") or "")
        script = """
tell application "Google Chrome"
  if (count of windows) is 0 then return "no_window"
  set targetWindowIndex to %d
  set targetTabIndex to %d
  set titleNeedle to %s
  set urlNeedle to %s
  if targetWindowIndex > 0 and targetWindowIndex <= (count of windows) then
    set candidateWindow to window targetWindowIndex
    set index of candidateWindow to 1
    if targetTabIndex > 0 and targetTabIndex <= (count of tabs of candidateWindow) then
      set active tab index of candidateWindow to targetTabIndex
      activate
      return "activated"
    end if
  end if
  if titleNeedle is not "" or urlNeedle is not "" then
    repeat with wi from 1 to count of windows
      set candidateWindow to window wi
      repeat with ti from 1 to count of tabs of candidateWindow
        set candidateTab to tab ti of candidateWindow
        set tabTitle to ""
        set tabUrl to ""
        try
          set tabTitle to title of candidateTab
          set tabUrl to URL of candidateTab
        end try
        if (titleNeedle is not "" and tabTitle contains titleNeedle) or (urlNeedle is not "" and tabUrl contains urlNeedle) then
          set index of candidateWindow to 1
          set active tab index of candidateWindow to ti
          activate
          return "activated"
        end if
      end repeat
    end repeat
  end if
  activate
  return "activated"
end tell
""" % (window_index, tab_index, json.dumps(title_contains), json.dumps(url_contains))
        try:
            completed = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
            return "activated" in (completed.stdout or "")
        except Exception:
            return False

    def _chrome_background_failure_reason(self, fallback: str) -> str:
        detail = str(getattr(self, "_last_background_error", "") or "").strip()
        if "JavaScript" in detail and ("AppleScript" in detail or "Apple Events" in detail):
            return (
                "Chrome background entry failed because Chrome has disabled JavaScript from Apple Events. "
                "Enable View > Developer > Allow JavaScript from Apple Events for true background control of the existing Chrome tab."
            )
        if detail:
            return f"{fallback} {detail}"
        return (
            f"{fallback} Enable Chrome's 'Allow JavaScript from Apple Events' setting "
            "or use an explicitly approved foreground fallback."
        )

    def _chrome_background_control(self, chrome_tabs: list[dict[str, Any]]) -> dict[str, Any]:
        if not chrome_tabs:
            return {"available": False, "reason": "Google Chrome tabs were not visible to AppleScript."}
        selected = next((tab for tab in chrome_tabs if "chatgpt.com" in str(tab.get("url") or "").lower()), None)
        selected = selected or chrome_tabs[0]
        payload = {
            "window_index": selected.get("window_index"),
            "tab_index": selected.get("tab_index"),
            "url_contains": "chatgpt.com" if "chatgpt.com" in str(selected.get("url") or "").lower() else selected.get("url"),
            "title_contains": selected.get("title"),
        }
        try:
            self._last_background_error = ""
            self._darwin_execute_chrome_background_js("document.title", payload)
        except Exception:
            return {
                "available": False,
                "reason": self._chrome_background_failure_reason("Chrome background JavaScript probe failed."),
                "recovery": {
                    "kind": "chrome_setting",
                    "setting": "Allow JavaScript from Apple Events",
                    "path": "View > Developer > Allow JavaScript from Apple Events",
                },
            }
        return {"available": True, "target": payload}

    def _darwin_type_in_chrome_background(self, text: str, payload: dict[str, Any]) -> bool:
        if not text:
            return True
        js = r"""
(function() {
  const text = %s;
  const candidates = [
    document.querySelector('#prompt-textarea'),
    document.querySelector('[data-testid="composer-root"] textarea'),
    document.querySelector('textarea'),
    document.querySelector('[contenteditable="true"]')
  ].filter(Boolean);
  const el = candidates.find((node) => {
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }) || candidates[0];
  if (!el) return 'composer_not_found';
  el.focus();
  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
    el.value = text;
  } else {
    el.textContent = text;
  }
  el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return 'typed';
})();
""" % json.dumps(text)
        try:
            self._last_background_error = ""
            return "typed" in self._darwin_execute_chrome_background_js(js, payload)
        except Exception:
            return False

    def _darwin_key_in_chrome_background(self, key: str, modifiers: list[Any], payload: dict[str, Any]) -> bool:
        normalized_modifiers = {str(item).strip().lower() for item in modifiers}
        command_down = bool(normalized_modifiers.intersection({"command", "cmd", "meta", "super"}))
        if command_down and key == "a":
            return True
        if key not in {"backspace", "delete", "del"}:
            return False
        js = r"""
(function() {
  const candidates = [
    document.querySelector('#prompt-textarea'),
    document.querySelector('[data-testid="composer-root"] textarea'),
    document.querySelector('textarea'),
    document.querySelector('[contenteditable="true"]')
  ].filter(Boolean);
  const el = candidates.find((node) => {
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }) || candidates[0];
  if (!el) return 'composer_not_found';
  el.focus();
  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
    el.value = '';
  } else {
    el.textContent = '';
  }
  el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward' }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return 'cleared';
})();
"""
        try:
            self._last_background_error = ""
            return "cleared" in self._darwin_execute_chrome_background_js(js, payload)
        except Exception:
            return False

    def _capture_action_result_screenshot(self, payload: dict[str, Any], marker: dict[str, Any] | None) -> dict[str, Any]:
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        path = self._artifact_root / f"click-{int(time.time() * 1000)}.png"
        capture = self._capture_screenshot(path, payload)
        if not capture.get("supported", True):
            return {}
        model_path = self._model_screenshot_copy(path)
        system = capture.get("platform", platform.system())
        result = self._screenshot_result(path, model_path, system, capture_target=capture.get("target_window"))
        result["action"] = "computer.click"
        result["screenshot_path"] = str(path)
        result["model_image_path"] = str(model_path)
        data_url = self._image_data_url(model_path)
        if data_url:
            result["data_url"] = data_url
        if marker:
            result["click_marker"] = marker
        return result

    def _capture_screenshot(self, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        system = platform.system()
        target = self._capture_target(payload)
        chrome_target = None
        if target is None and self._has_window_filter(payload) and self._payload_targets_chrome(payload):
            chrome_target = self._select_chrome_tab(payload)
            if chrome_target and self._allow_foreground_fallback(payload):
                if self._activate_chrome_target(payload):
                    time.sleep(0.25)
                    target = self._capture_target(payload)
        explicit_desktop = str(payload.get("target") or payload.get("capture_target") or "").strip().lower() in {
            "primary_display",
            "all_displays",
            "screen",
            "display",
            "desktop",
        }
        if target is None and self._has_window_filter(payload) and not explicit_desktop:
            reason = "No visible window matched the requested app/title; refusing to capture the front desktop because it would mislead the model."
            recovery = None
            if chrome_target:
                reason = (
                    "A matching Google Chrome tab was found, but no visible Chrome window was available for a window-scoped screenshot. "
                    "Allow foreground fallback to activate the existing Chrome tab, or use background DOM entry when Chrome permits it."
                )
                recovery = {
                    "kind": "foreground_fallback",
                    "note": "Set allow_foreground_fallback=true or input_overlap_ok=true when the user permits switching to the existing app.",
                }
            return {
                "platform": system,
                "supported": False,
                "reason": reason,
                "target_filter": self._window_filter(payload),
                **({"chrome_target": chrome_target, "background_target_only": True} if chrome_target else {}),
                **({"recovery": recovery} if recovery else {}),
            }
        if system == "Darwin":
            if target:
                window_id = target.get("window_id")
                if window_id:
                    subprocess.run(["screencapture", "-x", "-l", str(int(window_id)), str(path)], check=True)
                else:
                    rect = "{},{},{},{}".format(
                        int(target.get("x", 0)),
                        int(target.get("y", 0)),
                        int(target.get("width", 0)),
                        int(target.get("height", 0)),
                    )
                    subprocess.run(["screencapture", "-x", "-R", rect, str(path)], check=True)
            else:
                subprocess.run(["screencapture", "-x", str(path)], check=True)
            return {"platform": system, "target_window": target}
        if system == "Windows":
            self._windows_screenshot(path, target=target)
            return {"platform": system, "target_window": target}
        return {"platform": system, "supported": False}

    def _capture_target(self, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        payload = payload or {}
        target = str(payload.get("target") or payload.get("capture_target") or "").strip().lower()
        if target in {"primary_display", "all_displays", "screen", "display", "desktop"}:
            return None
        if target in {"active_window", "front_window"}:
            return self._active_window()
        if isinstance(payload.get("window"), dict):
            selected = self._normalize_window_record(payload.get("window"))
            return selected if self._is_usable_target_window(selected) else None
        if self._has_window_filter(payload):
            selected = self._matching_window(payload)
            if selected is not None:
                state = self._computer_state()
                state["target_window"] = selected
                self._write_computer_state(state)
                return selected
            return None
        selected = self._computer_state().get("target_window")
        if target in {"selected_window", "window", "app"} or (not target and isinstance(selected, dict)):
            selected = self._normalize_window_record(selected)
            if self._is_usable_target_window(selected):
                return selected
            self._clear_target_window()
        return None

    @staticmethod
    def _window_filter(payload: dict[str, Any] | None = None) -> dict[str, str]:
        payload = payload or {}
        app = str(payload.get("app") or payload.get("application") or "").strip()
        title = str(payload.get("title") or payload.get("title_contains") or "").strip()
        return {"app": app, "title": title}

    def _has_window_filter(self, payload: dict[str, Any] | None = None) -> bool:
        filters = self._window_filter(payload)
        return bool(filters.get("app") or filters.get("title"))

    def _matching_window(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        filters = self._window_filter(payload)
        app = filters.get("app", "").lower()
        title = filters.get("title", "").lower()
        selected = self._normalize_window_record(self._computer_state().get("target_window"))
        if selected and self._is_usable_target_window(selected) and self._window_matches_filter(selected, app=app, title=title):
            return selected
        for item in self._list_windows():
            window = self._normalize_window_record(item)
            if window and self._is_usable_target_window(window) and self._window_matches_filter(window, app=app, title=title):
                return window
        return None

    def _resolve_action_point(self, payload: dict[str, Any], *, infer_window: bool = False) -> tuple[dict[str, Any], dict[str, Any] | None]:
        state = self._computer_state()
        cursor = state.get("ai_cursor") if isinstance(state.get("ai_cursor"), dict) else {}
        x = int(payload.get("x", cursor.get("x", 0)))
        y = int(payload.get("y", cursor.get("y", 0)))
        target = self._capture_target(payload)
        if target is None and infer_window:
            target = self._window_at_point(x, y)
            if target is not None:
                state["target_window"] = target
                self._write_computer_state(state)
        coordinate_space = str(payload.get("coordinate_space") or payload.get("space") or "auto").strip().lower()
        use_window_space = False
        if target and coordinate_space in {"auto", "window", "target", "screenshot", "image"}:
            width = int(target.get("width", 0))
            height = int(target.get("height", 0))
            use_window_space = 0 <= x <= max(width, 0) and 0 <= y <= max(height, 0)
        action_payload = dict(payload)
        if target and use_window_space:
            screen_x = int(target.get("x", 0)) + x
            screen_y = int(target.get("y", 0)) + y
            action_payload["x"] = screen_x
            action_payload["y"] = screen_y
            marker = {
                "x": x,
                "y": y,
                "screen_x": screen_x,
                "screen_y": screen_y,
                "coordinate_space": "screenshot_image",
            }
        else:
            action_payload["x"] = x
            action_payload["y"] = y
            marker = {"x": x, "y": y, "screen_x": x, "screen_y": y, "coordinate_space": "screen"}
            if target:
                marker["x"] = x - int(target.get("x", 0))
                marker["y"] = y - int(target.get("y", 0))
                marker["coordinate_space"] = "screenshot_image"
        self._set_ai_cursor(action_payload)
        return action_payload, marker

    def _computer_state(self) -> dict[str, Any]:
        sessions = self._read_sessions()
        state = sessions.get("computer") if isinstance(sessions.get("computer"), dict) else {}
        return dict(state)

    def _write_computer_state(self, state: dict[str, Any]) -> None:
        sessions = self._read_sessions()
        sessions["computer"] = state
        sessions["updated_at"] = self._now_iso()
        self._write_sessions(sessions)

    def _clear_target_window(self) -> None:
        state = self._computer_state()
        if "target_window" in state:
            state.pop("target_window", None)
            self._write_computer_state(state)

    def _set_ai_cursor(self, payload: dict[str, Any]) -> None:
        state = self._computer_state()
        state["ai_cursor"] = {
            "x": int(payload.get("x", 0)),
            "y": int(payload.get("y", 0)),
            "origin": "top_left",
            "updated_at": self._now_iso(),
        }
        self._write_computer_state(state)

    def _window_at_point(self, x: int, y: int) -> dict[str, Any] | None:
        for item in self._list_windows():
            window = self._normalize_window_record(item)
            if window is None:
                continue
            left = int(window.get("x", 0))
            top = int(window.get("y", 0))
            right = left + int(window.get("width", 0))
            bottom = top + int(window.get("height", 0))
            if left <= x <= right and top <= y <= bottom:
                return window
        return None

    def _select_window(self, payload: dict[str, Any]) -> dict[str, Any]:
        windows = self._list_windows()
        target = str(payload.get("target") or "").strip().lower()
        app = str(payload.get("app") or payload.get("application") or "").strip().lower()
        title = str(payload.get("title") or "").strip().lower()
        has_filter = bool(app or title or isinstance(payload.get("window"), dict))
        selected = None
        if isinstance(payload.get("window"), dict):
            selected = self._normalize_window_record(payload.get("window"))
        if selected is None and target in {"selected", "selected_window", "window", "app"}:
            selected = self._computer_state().get("target_window")
        if selected is None and (target in {"active", "active_window", "front", "front_window"} or (not target and not has_filter)):
            selected = next((item for item in windows if item.get("active")), None) or self._active_window()
        if selected is None:
            for item in windows:
                item_app = str(item.get("app") or "").lower()
                item_title = str(item.get("title") or "").lower()
                if app and app not in item_app:
                    continue
                if title and title not in item_title:
                    continue
                if not self._is_usable_target_window(item):
                    continue
                selected = item
                break
        if selected is None:
            if app and "chrome" in app:
                chrome_target = self._select_chrome_tab(payload)
                if chrome_target:
                    self._clear_target_window()
                    return {
                        "action": "computer.select_window",
                        "selected": True,
                        "target_window": None,
                        "chrome_target": chrome_target,
                        "windows": windows,
                        "chrome_tabs": self._chrome_tabs(),
                        "background_target_only": True,
                        "reason": "Google Chrome is open, but no visible window was available in the current app-window context. Stored a Chrome tab target for background-capable actions.",
                    }
            if has_filter:
                self._clear_target_window()
            return {"action": "computer.select_window", "selected": False, "windows": windows}
        selected = self._normalize_window_record(selected)
        if selected is None or not self._is_usable_target_window(selected):
            if has_filter:
                self._clear_target_window()
            return {"action": "computer.select_window", "selected": False, "windows": windows}
        state = self._computer_state()
        state["target_window"] = selected
        self._write_computer_state(state)
        if payload.get("focus", True) is not False:
            self._focus_window(selected)
        return {
            "action": "computer.select_window",
            "selected": True,
            "target_window": selected,
            "windows": windows,
            "coordinate_space": "screenshot_image",
        }

    def _list_windows(self) -> list[dict[str, Any]]:
        system = platform.system()
        if system == "Darwin":
            return self._darwin_windows()
        if system == "Windows":
            active = self._windows_active_window()
            return [active] if active else []
        return []

    def _active_window(self) -> dict[str, Any] | None:
        system = platform.system()
        if system == "Darwin":
            windows = self._darwin_windows()
            return next((item for item in windows if item.get("active")), None)
        if system == "Windows":
            return self._windows_active_window()
        return None

    @staticmethod
    def _normalize_window_record(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        try:
            x = int(float(value.get("x", 0)))
            y = int(float(value.get("y", 0)))
            width = int(float(value.get("width", 0)))
            height = int(float(value.get("height", 0)))
        except Exception:
            return None
        if width <= 0 or height <= 0:
            return None
        normalized = {
            "app": str(value.get("app") or value.get("process") or ""),
            "title": str(value.get("title") or value.get("name") or ""),
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "active": bool(value.get("active")),
        }
        window_id = value.get("window_id") or value.get("id")
        try:
            if window_id is not None:
                normalized["window_id"] = int(window_id)
        except Exception:
            pass
        return normalized

    @staticmethod
    def _is_usable_target_window(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        try:
            width = int(float(value.get("width", 0)))
            height = int(float(value.get("height", 0)))
        except Exception:
            return False
        return width >= 200 and height >= 120

    def _darwin_windows(self) -> list[dict[str, Any]]:
        quartz_windows = self._darwin_windows_quartz()
        if quartz_windows:
            return quartz_windows
        script = r'''
tell application "System Events"
  set output to ""
  repeat with proc in (application processes whose background only is false)
    set procName to name of proc
    set procFront to frontmost of proc
    repeat with win in windows of proc
      try
        set winName to name of win
        set winPos to position of win
        set winSize to size of win
        set output to output & procName & tab & winName & tab & (item 1 of winPos) & tab & (item 2 of winPos) & tab & (item 1 of winSize) & tab & (item 2 of winSize) & tab & procFront & linefeed
      end try
    end repeat
  end repeat
  return output
end tell
'''
        try:
            completed = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        except Exception:
            return []
        windows: list[dict[str, Any]] = []
        for line in completed.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            try:
                window = {
                    "app": parts[0],
                    "title": parts[1],
                    "x": int(float(parts[2])),
                    "y": int(float(parts[3])),
                    "width": int(float(parts[4])),
                    "height": int(float(parts[5])),
                    "active": parts[6].strip().lower() == "true",
                }
            except Exception:
                continue
            if window["width"] > 0 and window["height"] > 0:
                windows.append(window)
        return windows

    @staticmethod
    def _frontmost_app_name() -> str:
        try:
            completed = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return (completed.stdout or "").strip()
        except Exception:
            return ""

    def _darwin_windows_quartz(self) -> list[dict[str, Any]]:
        code = r"""
import json
import Quartz

options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
items = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
windows = []
for item in items:
    if int(item.get("kCGWindowLayer", 0) or 0) != 0:
        continue
    bounds = item.get("kCGWindowBounds") or {}
    width = int(round(float(bounds.get("Width", 0) or 0)))
    height = int(round(float(bounds.get("Height", 0) or 0)))
    if width <= 0 or height <= 0:
        continue
    windows.append({
        "app": str(item.get("kCGWindowOwnerName") or ""),
        "title": str(item.get("kCGWindowName") or ""),
        "x": int(round(float(bounds.get("X", 0) or 0))),
        "y": int(round(float(bounds.get("Y", 0) or 0))),
        "width": width,
        "height": height,
        "window_id": int(item.get("kCGWindowNumber", 0) or 0),
    })
print(json.dumps(windows))
"""
        try:
            completed = subprocess.run(["python3", "-c", code], check=True, capture_output=True, text=True)
            windows = json.loads(completed.stdout or "[]")
        except Exception:
            return []
        frontmost = self._frontmost_app_name().lower()
        normalized = []
        for item in windows:
            window = self._normalize_window_record(item)
            if window is None:
                continue
            window["active"] = bool(frontmost and str(window.get("app") or "").lower() == frontmost)
            normalized.append(window)
        return normalized

    def _focus_window(self, window: dict[str, Any]) -> None:
        raw_app = str(window.get("app") or "")
        raw_title = str(window.get("title") or "")
        if platform.system() == "Darwin" and "chrome" in raw_app.lower() and raw_title:
            if self._activate_chrome_target({"app": raw_app, "title_contains": raw_title}):
                return
        app = raw_app.replace('"', '\\"')
        if not app:
            return
        if platform.system() == "Darwin":
            script = """
tell application "System Events"
  set appName to %s
  set titleNeedle to %s
  tell application process appName
    set frontmost to true
    if titleNeedle is not "" then
      repeat with candidateWindow in windows
        try
          if (name of candidateWindow) contains titleNeedle then
            perform action "AXRaise" of candidateWindow
            exit repeat
          end if
        end try
      end repeat
    end if
  end tell
end tell
""" % (json.dumps(raw_app), json.dumps(raw_title))
            try:
                subprocess.run(["osascript", "-e", script], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def _darwin_move_cursor(self, payload: dict[str, Any]) -> None:
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))
        cliclick = shutil.which("cliclick")
        if cliclick:
            subprocess.run([cliclick, f"m:{x},{y}"], check=True)
            return
        code = (
            "import Quartz, sys\n"
            f"Quartz.CGWarpMouseCursorPosition(({x}, {y}))\n"
            "Quartz.CGAssociateMouseAndMouseCursorPosition(True)\n"
        )
        try:
            subprocess.run(["python3", "-c", code], check=True)
        except Exception as exc:
            raise RuntimeError("computer.move requires cliclick or PyObjC Quartz on macOS") from exc

    def _darwin_click(self, payload: dict[str, Any]) -> None:
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))
        button = str(payload.get("button") or "left").lower()
        button_index = 1 if button in {"right", "secondary"} else 0
        down_event = "kCGEventRightMouseDown" if button_index == 1 else "kCGEventLeftMouseDown"
        up_event = "kCGEventRightMouseUp" if button_index == 1 else "kCGEventLeftMouseUp"
        code = (
            "import Quartz\n"
            f"point = Quartz.CGPoint({x}, {y})\n"
            f"down = Quartz.CGEventCreateMouseEvent(None, Quartz.{down_event}, point, {button_index})\n"
            f"up = Quartz.CGEventCreateMouseEvent(None, Quartz.{up_event}, point, {button_index})\n"
            "Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)\n"
            "Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)\n"
        )
        try:
            subprocess.run(["python3", "-c", code], check=True)
        except Exception:
            script = self._apple_script("computer.click", payload)
            subprocess.run(["osascript", "-e", script], check=True)

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

    def _windows_screenshot(self, path: Path, target: dict[str, Any] | None = None) -> None:
        escaped = self._ps_single(str(path))
        bounds_script = (
            "$bounds = New-Object System.Drawing.Rectangle({}, {}, {}, {})".format(
                int(target.get("x", 0)),
                int(target.get("y", 0)),
                int(target.get("width", 0)),
                int(target.get("height", 0)),
            )
            if target
            else "$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds"
        )
        script = "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "Add-Type -AssemblyName System.Windows.Forms",
                "Add-Type -AssemblyName System.Drawing",
                bounds_script,
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
        if action == "computer.move":
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
            self._run_powershell("\n".join(prelude + [f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})"]))
            return
        if action == "computer.click":
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
            restore_cursor = payload.get("isolate_cursor", True) is not False
            script = "\n".join(
                prelude
                + [
                    "Add-Type -TypeDefinition @'\nusing System;\nusing System.Runtime.InteropServices;\npublic class RumiMouse {\n  [DllImport(\"user32.dll\")]\n  public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);\n}\n'@",
                    "$original = [System.Windows.Forms.Cursor]::Position",
                    f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})",
                    "[RumiMouse]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)",
                    "[RumiMouse]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)",
                    "[System.Windows.Forms.Cursor]::Position = $original" if restore_cursor else "",
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

    def _windows_active_window(self) -> dict[str, Any] | None:
        script = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class RumiWindow {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
'@
$h = [RumiWindow]::GetForegroundWindow()
$r = New-Object RumiWindow+RECT
[void][RumiWindow]::GetWindowRect($h, [ref]$r)
$titleBuilder = New-Object System.Text.StringBuilder 512
[void][RumiWindow]::GetWindowText($h, $titleBuilder, $titleBuilder.Capacity)
ConvertTo-Json @{ app = ""; title = $titleBuilder.ToString(); x = $r.Left; y = $r.Top; width = ($r.Right - $r.Left); height = ($r.Bottom - $r.Top); active = $true } -Compress
'''
        try:
            executable = "powershell" if shutil.which("powershell") else "pwsh"
            completed = subprocess.run([executable, "-NoProfile", "-Command", script], check=True, capture_output=True, text=True)
            value = json.loads(completed.stdout or "{}")
            return self._normalize_window_record(value)
        except Exception:
            return None

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
            "browser_persistent_profiles": True,
            "browser_cookie_management": True,
            "browser_cache_management": True,
            "screenshot": system in {"Darwin", "Windows"},
            "window_selection": system in {"Darwin", "Windows"},
            "desktop_actions": system in {"Darwin", "Windows"},
            "cursor_move": system in {"Darwin", "Windows"},
            "virtual_ai_cursor": True,
            "driver_auto_switch": system in {"Darwin", "Windows"},
            "foreground_input_fallback": system in {"Darwin", "Windows"},
            "chrome_background_dom": system == "Darwin",
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

    @staticmethod
    def _now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _active_profile_id(self) -> str:
        sessions = self._read_sessions()
        return self._profile_id(sessions.get("active_profile_id") or "default")

    def _list_profiles(self) -> list[dict[str, Any]]:
        sessions = self._read_sessions()
        profiles = sessions.get("profiles") if isinstance(sessions.get("profiles"), dict) else {}
        self._ensure_profile("default", label="Default")
        sessions = self._read_sessions()
        profiles = sessions.get("profiles") if isinstance(sessions.get("profiles"), dict) else {}
        return [
            self._profile_summary(profile_id, record)
            for profile_id, record in sorted(profiles.items())
            if isinstance(record, dict)
        ]

    def _ensure_profile(self, profile_id: str, *, label: str | None = None) -> dict[str, Any]:
        profile_id = self._profile_id(profile_id)
        sessions = self._read_sessions()
        profiles = sessions.get("profiles") if isinstance(sessions.get("profiles"), dict) else {}
        now = self._now_iso()
        record = profiles.get(profile_id) if isinstance(profiles.get(profile_id), dict) else {}
        if not record:
            record = {"id": profile_id, "label": label or profile_id, "created_at": now}
        elif label:
            record["label"] = label
        record["profile_dir"] = str(self._profile_path(profile_id) / "browser-data")
        record["cache_dir"] = str(self._profile_path(profile_id) / "cache")
        record["cookie_jar"] = str(self._cookie_jar_path(profile_id))
        record["updated_at"] = now
        profiles[profile_id] = record
        sessions["profiles"] = profiles
        sessions.setdefault("active_profile_id", profile_id if profile_id != "default" else "default")
        sessions["updated_at"] = now
        self._write_sessions(sessions)
        (self._profile_path(profile_id) / "browser-data").mkdir(parents=True, exist_ok=True)
        (self._profile_path(profile_id) / "cache").mkdir(parents=True, exist_ok=True)
        return record

    def _profile_summary(self, profile_id: str, record: dict[str, Any]) -> dict[str, Any]:
        cookie_jar = self._read_cookie_jar(profile_id)
        cache_paths = [path for path in self._cache_paths(profile_id) if path.exists()]
        return {
            "id": profile_id,
            "label": record.get("label") or profile_id,
            "profile_dir": record.get("profile_dir") or str(self._profile_path(profile_id) / "browser-data"),
            "cache_dir": record.get("cache_dir") or str(self._profile_path(profile_id) / "cache"),
            "cookie_jar": str(self._cookie_jar_path(profile_id)),
            "managed_cookie_count": len(cookie_jar.get("cookies", [])),
            "cache_size_bytes": sum(self._path_size(path) for path in cache_paths),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }

    def _profile_path(self, profile_id: str) -> Path:
        return self._profile_root / self._profile_id(profile_id)

    @staticmethod
    def _profile_id(value: Any) -> str:
        raw = str(value or "default").strip().lower()
        cleaned = re.sub(r"[^a-z0-9._-]+", "-", raw).strip(".-_")
        return (cleaned or "default")[:64]

    def _browser_launch_plan(self, url: str, profile_id: str, *, persistent: bool) -> dict[str, Any]:
        executable = self._find_browser_executable()
        profile_path = self._profile_path(profile_id)
        browser_data = profile_path / "browser-data"
        cache_dir = profile_path / "cache"
        if not persistent:
            return {"mode": "default_browser", "reason": "persistent=false"}
        if not executable:
            return {"mode": "default_browser", "reason": "no_supported_browser_found"}
        return {
            "mode": "managed_profile",
            "browser": str(executable),
            "profile_id": profile_id,
            "profile_dir": str(browser_data),
            "cache_dir": str(cache_dir),
            "command": [
                str(executable),
                f"--user-data-dir={browser_data}",
                f"--disk-cache-dir={cache_dir}",
                "--new-window",
                url,
            ],
        }

    def _find_browser_executable(self) -> Path | None:
        system = platform.system()
        candidates: list[Path] = []
        if system == "Darwin":
            candidates = [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path.home() / "Applications" / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome",
            ]
        elif system == "Windows":
            roots = [
                os.environ.get("LOCALAPPDATA"),
                os.environ.get("PROGRAMFILES"),
                os.environ.get("PROGRAMFILES(X86)"),
            ]
            for root in [Path(value) for value in roots if value]:
                candidates.extend(
                    [
                        root / "Google" / "Chrome" / "Application" / "chrome.exe",
                        root / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                    ]
                )
        else:
            for name in ["google-chrome", "chromium", "chromium-browser", "microsoft-edge"]:
                resolved = shutil.which(name)
                if resolved:
                    candidates.append(Path(resolved))
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _cache_paths(self, profile_id: str) -> list[Path]:
        base = self._profile_path(profile_id)
        default_profile = base / "browser-data" / "Default"
        return [
            base / "cache",
            default_profile / "Cache",
            default_profile / "Code Cache",
            default_profile / "GPUCache",
            default_profile / "Service Worker" / "CacheStorage",
        ]

    def _browser_cookie_paths(self, profile_id: str) -> list[Path]:
        default_profile = self._profile_path(profile_id) / "browser-data" / "Default"
        return [
            default_profile / "Cookies",
            default_profile / "Cookies-journal",
            default_profile / "Network" / "Cookies",
            default_profile / "Network" / "Cookies-journal",
        ]

    def _cookie_jar_path(self, profile_id: str) -> Path:
        return self._profile_path(profile_id) / "managed_cookies.json"

    def _read_cookie_jar(self, profile_id: str) -> dict[str, Any]:
        try:
            value = json.loads(self._cookie_jar_path(profile_id).read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("cookies"), list):
                return value
        except Exception:
            pass
        return {"version": 1, "cookies": []}

    def _write_cookie_jar(self, profile_id: str, value: dict[str, Any]) -> None:
        self._profile_path(profile_id).mkdir(parents=True, exist_ok=True)
        self._cookie_jar_path(profile_id).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
        name = str(cookie.get("name") or "").strip()
        domain = str(cookie.get("domain") or cookie.get("url") or "").strip()
        if not name or not domain:
            raise ValueError("cookie.name and cookie.domain are required")
        return {
            "name": name,
            "value": str(cookie.get("value") or ""),
            "domain": domain,
            "path": str(cookie.get("path") or "/"),
            "expires": cookie.get("expires"),
            "httpOnly": bool(cookie.get("httpOnly") or cookie.get("http_only")),
            "secure": bool(cookie.get("secure")),
            "sameSite": cookie.get("sameSite") or cookie.get("same_site"),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    @staticmethod
    def _merge_cookies(current: list[Any], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for cookie in current:
            if not isinstance(cookie, dict):
                continue
            key = (str(cookie.get("domain") or ""), str(cookie.get("path") or "/"), str(cookie.get("name") or ""))
            if key[2]:
                merged[key] = cookie
        for cookie in incoming:
            merged[(cookie["domain"], cookie["path"], cookie["name"])] = cookie
        return list(merged.values())

    @staticmethod
    def _cookie_public_view(cookie: dict[str, Any], *, include_values: bool) -> dict[str, Any]:
        view = {key: value for key, value in cookie.items() if key != "value"}
        value = str(cookie.get("value") or "")
        view["value"] = value if include_values else ("***" if value else "")
        view["value_redacted"] = not include_values and bool(value)
        return view

    @staticmethod
    def _cookie_matches(cookie: dict[str, Any], *, name: str, domain: str, path: str) -> bool:
        if name and cookie.get("name") != name:
            return False
        if domain and cookie.get("domain") != domain:
            return False
        if path and cookie.get("path") != path:
            return False
        return bool(name or domain or path)

    def _path_size(self, path: Path) -> int:
        try:
            if path.is_file():
                return path.stat().st_size
            if not path.exists():
                return 0
            total = 0
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
            return total
        except Exception:
            return 0

    @staticmethod
    def _remove_path(path: Path) -> bool:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

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
