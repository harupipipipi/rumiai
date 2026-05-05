from __future__ import annotations

import json
import os
import platform
import re
import shutil
import struct
import subprocess
import time
import webbrowser
import base64
from pathlib import Path
from typing import Any

from domain.approval.store import ApprovalStore, approval_store_path, classify_approval_risk


class BrowserComputerController:
    """Generic browser/computer action controller with approval gates."""

    def __init__(self, artifact_root: Path | None = None) -> None:
        pack_root = Path(__file__).resolve().parents[2]
        self._artifact_root = artifact_root or pack_root / "user_data" / "artifacts" / "computer"
        self._session_path = pack_root / "user_data" / "shared" / "browser_sessions.json"
        self._approval_path = approval_store_path()
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
        if action == "computer.health":
            return self._computer_health()
        if action == "computer.permissions":
            return {"action": action, "platform": platform.system(), "preflight": self._preflight()}
        if action == "computer.displays.list":
            return self._list_displays()
        if action == "computer.active_window":
            return self._active_window()
        if action == "computer.windows.list":
            return self._list_windows(payload)
        if action == "computer.screenshot":
            return self._screenshot(payload=payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action in {
            "computer.move",
            "computer.click",
            "computer.type",
            "computer.key",
            "computer.scroll",
            "computer.window.focus",
            "computer.window.bounds",
            "computer.hotkey",
            "computer.clipboard.read",
            "computer.clipboard.write",
            "computer.app.open",
            "computer.app.focus",
        }:
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
            webbrowser.open(url)
        sessions = self._read_sessions()
        sessions["last_url"] = url
        sessions["active_profile_id"] = profile_id
        sessions["last_opened_with_managed_profile"] = opened_with_managed_profile
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
        }

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

    def _computer_health(self) -> dict[str, Any]:
        system = platform.system()
        return {
            "action": "computer.health",
            "platform": system,
            "supported": system in {"Darwin", "Windows"},
            "capabilities": self._capabilities(),
            "preflight": self._preflight(),
            "risk": {
                "read_only": classify_approval_risk("computer.permissions"),
                "desktop_action": classify_approval_risk("computer.click", {"x": 0, "y": 0}),
                "high_risk": classify_approval_risk("computer.clipboard.write", {"text": ""}),
            },
        }

    def _preflight(self) -> dict[str, Any]:
        system = platform.system()
        if system == "Darwin":
            return self._darwin_preflight()
        if system == "Windows":
            return self._windows_preflight()
        return {"platform_supported": {"available": False, "status": "unsupported"}}

    def _darwin_preflight(self) -> dict[str, Any]:
        quartz = self._python_module_preflight("Quartz")
        osascript = self._command_preflight("osascript", "/usr/bin/osascript")
        screencapture = self._command_preflight("screencapture", "/usr/sbin/screencapture")
        return {
            "screen_recording": self._darwin_screen_recording_preflight(quartz),
            "accessibility": self._darwin_accessibility_preflight(quartz),
            "automation_system_events": {
                "available": bool(osascript.get("available")),
                "status": "unknown" if osascript.get("available") else "missing_dependency",
                "reason": "macOS Automation permission is checked by System Events at execution time.",
            },
            "screencapture": screencapture,
            "osascript": osascript,
            "quartz": quartz,
            "cliclick": self._command_preflight("cliclick"),
        }

    def _windows_preflight(self) -> dict[str, Any]:
        powershell = self._command_preflight("powershell")
        pwsh = self._command_preflight("pwsh")
        probe = self._windows_preflight_probe() if powershell.get("available") or pwsh.get("available") else {}
        return {
            "powershell": powershell,
            "pwsh": pwsh,
            "forms": self._probe_status(probe, "forms"),
            "drawing": self._probe_status(probe, "drawing"),
            "desktop_session_active": self._probe_status(probe, "desktop_session_active"),
            "screen_locked": self._probe_status(probe, "screen_locked"),
            "dpi_scale": probe.get("dpi_scale") if isinstance(probe.get("dpi_scale"), (int, float)) else None,
        }

    def _list_displays(self) -> dict[str, Any]:
        system = platform.system()
        if system == "Darwin":
            displays = self._darwin_displays()
        elif system == "Windows":
            displays = self._windows_displays()
        else:
            displays = []
        return {
            "action": "computer.displays.list",
            "platform": system,
            "supported": system in {"Darwin", "Windows"},
            "displays": displays,
            "count": len(displays),
        }

    def _active_window(self) -> dict[str, Any]:
        system = platform.system()
        if system == "Darwin":
            window = self._darwin_active_window()
        elif system == "Windows":
            window = self._windows_active_window()
        else:
            window = None
        return {
            "action": "computer.active_window",
            "platform": system,
            "supported": system in {"Darwin", "Windows"},
            "window": window,
        }

    def _list_windows(self, payload: dict[str, Any]) -> dict[str, Any]:
        system = platform.system()
        limit = int(payload.get("limit") or 50)
        if system == "Darwin":
            windows = self._darwin_windows(limit)
        elif system == "Windows":
            windows = self._windows_windows(limit)
        else:
            windows = []
        return {
            "action": "computer.windows.list",
            "platform": system,
            "supported": system in {"Darwin", "Windows"},
            "windows": windows,
            "count": len(windows),
        }

    def _screenshot(self, *, payload: dict[str, Any], dry_run: bool, yolo_mode: bool) -> dict[str, Any]:
        if dry_run:
            return {"action": "computer.screenshot", "dry_run": True, "requires_approval": False}
        risk = classify_approval_risk("computer.screenshot", {})
        approved = yolo_mode or self._consume_approval(payload, "computer.screenshot", {}, risk=risk)
        if not approved:
            return self._approval_required("computer.screenshot", {}, risk=risk)
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
        result = self._screenshot_result(path, model_path, system)
        if data_url:
            result["data_url"] = data_url
            result["model_image_path"] = str(model_path)
        return result

    def _screenshot_result(self, path: Path, model_path: Path, system: str) -> dict[str, Any]:
        result: dict[str, Any] = {"action": "computer.screenshot", "path": str(path), "mime_type": "image/png", "platform": system}
        image_size = self._image_size(path)
        model_image_size = self._image_size(model_path)
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
        action_coordinate_system = self._action_coordinate_system(system, image_size)
        if action_coordinate_system:
            result["action_coordinate_system"] = action_coordinate_system
        display_metadata = self._screenshot_display_metadata(system, image_size)
        if display_metadata:
            result["display_metadata"] = display_metadata
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
        result["cursor_move_contract"] = {
            "tool": "browser_use",
            "action": "move",
            "screen_coordinates": True,
            "coordinate_source": "screenshot",
            "notes": "Call move with action_coordinate_system coordinates. If a point is estimated on model_image_size, multiply by model_to_action_scale before calling move.",
        }
        return result

    def _screenshot_display_metadata(self, system: str, image_size: tuple[int, int] | None) -> dict[str, Any] | None:
        displays: list[dict[str, Any]] = []
        if system == "Darwin":
            displays = self._darwin_displays()
        elif system == "Windows":
            displays = self._windows_displays()
        primary = next((display for display in displays if display.get("primary")), displays[0] if displays else None)
        if not primary and image_size:
            width, height = image_size
            primary = {
                "id": "captured",
                "primary": True,
                "bounds": {"x": 0, "y": 0, "width": width, "height": height},
                "pixel_size": {"width": width, "height": height},
                "dpi_scale": 1.0,
            }
        if not primary:
            return None
        metadata = {"primary": primary}
        if displays:
            metadata["displays"] = displays
        if image_size:
            metadata["captured_pixel_size"] = {"width": image_size[0], "height": image_size[1]}
            bounds = primary.get("bounds") if isinstance(primary.get("bounds"), dict) else {}
            width = bounds.get("width")
            height = bounds.get("height")
            if width and height:
                metadata["screenshot_to_display_scale"] = {
                    "x": image_size[0] / width,
                    "y": image_size[1] / height,
                }
        return metadata

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
    def _action_coordinate_system(system: str, image_size: tuple[int, int] | None) -> dict[str, Any] | None:
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

    @staticmethod
    def _command_preflight(name: str, fallback: str | None = None) -> dict[str, Any]:
        path = shutil.which(name)
        if not path and fallback and Path(fallback).exists():
            path = fallback
        return {"available": bool(path), "path": path, "status": "ok" if path else "missing"}

    @staticmethod
    def _python_module_preflight(module_name: str) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                ["python3", "-c", f"import {module_name}"],
                check=False,
                capture_output=True,
                text=True,
            )
            available = completed.returncode == 0
            return {"available": available, "status": "ok" if available else "missing"}
        except Exception:
            return {"available": False, "status": "missing"}

    def _darwin_screen_recording_preflight(self, quartz: dict[str, Any]) -> dict[str, Any]:
        if not quartz.get("available"):
            return {"available": False, "status": "unknown", "reason": "Quartz is unavailable."}
        code = (
            "import json, Quartz\n"
            "fn = getattr(Quartz, 'CGPreflightScreenCaptureAccess', None)\n"
            "value = None if fn is None else bool(fn())\n"
            "print(json.dumps({'available': value is not None, 'allowed': value, 'status': 'ok' if value else 'not_granted' if value is False else 'unknown'}))\n"
        )
        return self._python_json_probe(code, fallback={"available": True, "status": "unknown"})

    def _darwin_accessibility_preflight(self, quartz: dict[str, Any]) -> dict[str, Any]:
        if not quartz.get("available"):
            return {"available": False, "status": "unknown", "reason": "Quartz is unavailable."}
        code = (
            "import json, Quartz\n"
            "fn = getattr(Quartz, 'AXIsProcessTrusted', None)\n"
            "value = None if fn is None else bool(fn())\n"
            "print(json.dumps({'available': value is not None, 'allowed': value, 'status': 'ok' if value else 'not_granted' if value is False else 'unknown'}))\n"
        )
        return self._python_json_probe(code, fallback={"available": True, "status": "unknown"})

    @staticmethod
    def _python_json_probe(code: str, *, fallback: dict[str, Any]) -> dict[str, Any]:
        try:
            completed = subprocess.run(["python3", "-c", code], check=False, capture_output=True, text=True)
            value = json.loads(completed.stdout or "{}")
            return value if isinstance(value, dict) else dict(fallback)
        except Exception:
            return dict(fallback)

    @staticmethod
    def _probe_status(probe: dict[str, Any], key: str) -> dict[str, Any]:
        if key not in probe:
            return {"available": False, "status": "unknown"}
        value = probe.get(key)
        if key == "screen_locked":
            return {"available": True, "locked": bool(value), "status": "locked" if value else "unlocked"}
        if isinstance(value, bool):
            return {"available": True, "allowed": value, "status": "ok" if value else "not_granted"}
        return {"available": bool(value), "value": value, "status": "ok" if value else "unknown"}

    def _windows_preflight_probe(self) -> dict[str, Any]:
        script = "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "Add-Type -AssemblyName System.Windows.Forms",
                "Add-Type -AssemblyName System.Drawing",
                "$graphics = [System.Drawing.Graphics]::FromHwnd([IntPtr]::Zero)",
                "$locked = [bool](Get-Process logonui -ErrorAction SilentlyContinue)",
                "$scale = [double]($graphics.DpiX / 96.0)",
                "$graphics.Dispose()",
                "ConvertTo-Json @{ forms = $true; drawing = $true; desktop_session_active = [Environment]::UserInteractive; screen_locked = $locked; dpi_scale = $scale } -Compress",
            ]
        )
        return self._run_powershell_json(script)

    def _darwin_displays(self) -> list[dict[str, Any]]:
        code = (
            "import json, Quartz\n"
            "ids = []\n"
            "try:\n"
            "    result = Quartz.CGGetActiveDisplayList(16, None, None)\n"
            "    if isinstance(result, tuple) and len(result) >= 2 and result[1]:\n"
            "        count = int(result[2]) if len(result) > 2 else len(result[1])\n"
            "        ids = [int(x) for x in list(result[1])[:count]]\n"
            "except Exception:\n"
            "    ids = []\n"
            "main = int(Quartz.CGMainDisplayID())\n"
            "if not ids:\n"
            "    ids = [main]\n"
            "items = []\n"
            "for display_id in ids:\n"
            "    bounds = Quartz.CGDisplayBounds(display_id)\n"
            "    width = int(round(bounds.size.width))\n"
            "    height = int(round(bounds.size.height))\n"
            "    pixels_w = int(Quartz.CGDisplayPixelsWide(display_id))\n"
            "    pixels_h = int(Quartz.CGDisplayPixelsHigh(display_id))\n"
            "    scale = (pixels_w / width) if width else None\n"
            "    items.append({'id': str(display_id), 'primary': display_id == main, 'bounds': {'x': int(round(bounds.origin.x)), 'y': int(round(bounds.origin.y)), 'width': width, 'height': height}, 'pixel_size': {'width': pixels_w, 'height': pixels_h}, 'dpi_scale': scale})\n"
            "print(json.dumps(items))\n"
        )
        try:
            completed = subprocess.run(["python3", "-c", code], check=True, capture_output=True, text=True)
            value = json.loads(completed.stdout or "[]")
            return value if isinstance(value, list) else []
        except Exception:
            return []

    def _windows_displays(self) -> list[dict[str, Any]]:
        script = "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "Add-Type -AssemblyName System.Windows.Forms",
                "Add-Type -AssemblyName System.Drawing",
                "$graphics = [System.Drawing.Graphics]::FromHwnd([IntPtr]::Zero)",
                "$scale = [double]($graphics.DpiX / 96.0)",
                "$graphics.Dispose()",
                "$items = foreach ($screen in [System.Windows.Forms.Screen]::AllScreens) { @{ id = $screen.DeviceName; primary = [bool]$screen.Primary; bounds = @{ x = [int]$screen.Bounds.X; y = [int]$screen.Bounds.Y; width = [int]$screen.Bounds.Width; height = [int]$screen.Bounds.Height }; working_area = @{ x = [int]$screen.WorkingArea.X; y = [int]$screen.WorkingArea.Y; width = [int]$screen.WorkingArea.Width; height = [int]$screen.WorkingArea.Height }; pixel_size = @{ width = [int]$screen.Bounds.Width; height = [int]$screen.Bounds.Height }; dpi_scale = $scale } }",
                "ConvertTo-Json @($items) -Compress",
            ]
        )
        value = self._run_powershell_json(script)
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and value:
            return [value]
        return []

    def _darwin_active_window(self) -> dict[str, Any] | None:
        script = [
            'tell application "System Events"',
            "set frontApp to first application process whose frontmost is true",
            "set appName to name of frontApp as text",
            "set pidValue to unix id of frontApp as text",
            'set titleValue to ""',
            "set xValue to 0 as text",
            "set yValue to 0 as text",
            "set wValue to 0 as text",
            "set hValue to 0 as text",
            "if exists window 1 of frontApp then",
            "set titleValue to name of window 1 of frontApp as text",
            "set posValue to position of window 1 of frontApp",
            "set sizeValue to size of window 1 of frontApp",
            "set xValue to item 1 of posValue as text",
            "set yValue to item 2 of posValue as text",
            "set wValue to item 1 of sizeValue as text",
            "set hValue to item 2 of sizeValue as text",
            "end if",
            "return appName & tab & pidValue & tab & titleValue & tab & xValue & tab & yValue & tab & wValue & tab & hValue",
            "end tell",
        ]
        try:
            completed = self._run_osascript(script)
            return self._parse_window_line(completed.stdout.strip(), window_id="frontmost")
        except Exception:
            return None

    def _darwin_windows(self, limit: int) -> list[dict[str, Any]]:
        script = [
            'tell application "System Events"',
            'set output to ""',
            "repeat with proc in (application processes whose background only is false)",
            "set appName to name of proc as text",
            "set pidValue to unix id of proc as text",
            "repeat with win in windows of proc",
            "set titleValue to name of win as text",
            "set posValue to position of win",
            "set sizeValue to size of win",
            "set output to output & appName & tab & pidValue & tab & titleValue & tab & (item 1 of posValue as text) & tab & (item 2 of posValue as text) & tab & (item 1 of sizeValue as text) & tab & (item 2 of sizeValue as text) & linefeed",
            "end repeat",
            "end repeat",
            "return output",
            "end tell",
        ]
        try:
            completed = self._run_osascript(script)
        except Exception:
            return []
        windows = []
        for index, line in enumerate(completed.stdout.splitlines()):
            parsed = self._parse_window_line(line, window_id=str(index + 1))
            if parsed:
                windows.append(parsed)
            if len(windows) >= limit:
                break
        return windows

    def _windows_active_window(self) -> dict[str, Any] | None:
        script = self._windows_user32_prelude() + "\n".join(
            [
                "$hwnd = [RumiWindow]::GetForegroundWindow()",
                "if ($hwnd -eq [IntPtr]::Zero) { ConvertTo-Json $null -Compress; exit }",
                "$title = New-Object System.Text.StringBuilder 1024",
                "[void][RumiWindow]::GetWindowText($hwnd, $title, $title.Capacity)",
                "$rect = New-Object RumiRect",
                "[void][RumiWindow]::GetWindowRect($hwnd, [ref]$rect)",
                "$proc = Get-Process | Where-Object { $_.MainWindowHandle -eq $hwnd } | Select-Object -First 1",
                "ConvertTo-Json @{ id = $hwnd.ToInt64().ToString(); title = $title.ToString(); app = if ($proc) { $proc.ProcessName } else { '' }; pid = if ($proc) { [int]$proc.Id } else { 0 }; bounds = @{ x = [int]$rect.Left; y = [int]$rect.Top; width = [int]($rect.Right - $rect.Left); height = [int]($rect.Bottom - $rect.Top) } } -Compress",
            ]
        )
        value = self._run_powershell_json(script)
        return value if isinstance(value, dict) and value else None

    def _windows_windows(self, limit: int) -> list[dict[str, Any]]:
        script = self._windows_user32_prelude() + "\n".join(
            [
                "$items = New-Object System.Collections.Generic.List[object]",
                "$callback = [RumiWindow+EnumWindowsProc]{ param([IntPtr]$hwnd, [IntPtr]$lparam)",
                "  if (-not [RumiWindow]::IsWindowVisible($hwnd)) { return $true }",
                "  $title = New-Object System.Text.StringBuilder 1024",
                "  [void][RumiWindow]::GetWindowText($hwnd, $title, $title.Capacity)",
                "  if ([string]::IsNullOrWhiteSpace($title.ToString())) { return $true }",
                "  $rect = New-Object RumiRect",
                "  [void][RumiWindow]::GetWindowRect($hwnd, [ref]$rect)",
                "  $items.Add(@{ id = $hwnd.ToInt64().ToString(); title = $title.ToString(); bounds = @{ x = [int]$rect.Left; y = [int]$rect.Top; width = [int]($rect.Right - $rect.Left); height = [int]($rect.Bottom - $rect.Top) } })",
                f"  return $items.Count -lt {max(limit, 1)}",
                "}",
                "[void][RumiWindow]::EnumWindows($callback, [IntPtr]::Zero)",
                "ConvertTo-Json @($items) -Compress",
            ]
        )
        value = self._run_powershell_json(script)
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and value:
            return [value]
        return []

    @staticmethod
    def _parse_window_line(line: str, *, window_id: str) -> dict[str, Any] | None:
        parts = line.split("\t")
        if len(parts) < 7:
            return None
        app, pid, title, x, y, width, height = parts[:7]
        return {
            "id": window_id,
            "app": app,
            "pid": int(pid) if str(pid).isdigit() else 0,
            "title": title,
            "bounds": {
                "x": int(float(x or 0)),
                "y": int(float(y or 0)),
                "width": int(float(width or 0)),
                "height": int(float(height or 0)),
            },
        }

    @staticmethod
    def _run_osascript(lines: list[str]) -> subprocess.CompletedProcess:
        command = ["osascript"]
        for line in lines:
            command.extend(["-e", line])
        return subprocess.run(command, check=True, capture_output=True, text=True)

    @staticmethod
    def _windows_user32_prelude() -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            "Add-Type -TypeDefinition @'\n"
            "using System;\n"
            "using System.Text;\n"
            "using System.Runtime.InteropServices;\n"
            "public struct RumiRect { public int Left; public int Top; public int Right; public int Bottom; }\n"
            "public class RumiWindow {\n"
            "  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);\n"
            "  [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();\n"
            "  [DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr hWnd);\n"
            "  [DllImport(\"user32.dll\")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool repaint);\n"
            "  [DllImport(\"user32.dll\")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);\n"
            "  [DllImport(\"user32.dll\")] public static extern bool GetWindowRect(IntPtr hWnd, ref RumiRect rect);\n"
            "  [DllImport(\"user32.dll\")] public static extern bool IsWindowVisible(IntPtr hWnd);\n"
            "  [DllImport(\"user32.dll\")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);\n"
            "}\n"
            "'@\n"
        )

    def _run_powershell_json(self, script: str) -> Any:
        executable = "powershell" if shutil.which("powershell") else "pwsh"
        command = [executable, "-NoProfile"]
        if executable == "powershell":
            command.extend(["-ExecutionPolicy", "Bypass"])
        command.extend(["-Command", script])
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            return {}
        try:
            return json.loads(completed.stdout or "{}")
        except Exception:
            return {}

    def _desktop_action(self, action: str, payload: dict[str, Any], *, yolo_mode: bool) -> dict[str, Any]:
        dry_run = bool(payload.get("dry_run"))
        approval_payload = self._safe_payload(payload)
        risk = classify_approval_risk(action, approval_payload)
        if dry_run:
            return {"action": action, "dry_run": True, "requires_approval": False, "risk": risk, "payload": approval_payload}
        if risk.get("approval_required") and not (yolo_mode or self._consume_approval(payload, action, approval_payload, risk=risk)):
            return self._approval_required(action, approval_payload, risk=risk)
        system = platform.system()
        if system == "Darwin" and action == "computer.move":
            self._darwin_move_cursor(payload)
        elif system == "Darwin" and action == "computer.scroll":
            self._darwin_scroll(payload)
        elif system == "Darwin" and action == "computer.hotkey":
            subprocess.run(["osascript", "-e", self._darwin_hotkey_script(payload)], check=True)
        elif system == "Darwin" and action == "computer.clipboard.read":
            return self._darwin_clipboard_read()
        elif system == "Darwin" and action == "computer.clipboard.write":
            self._darwin_clipboard_write(payload)
        elif system == "Darwin" and action == "computer.window.focus":
            self._darwin_focus_window(payload)
        elif system == "Darwin" and action == "computer.window.bounds":
            self._darwin_set_window_bounds(payload)
        elif system == "Darwin" and action == "computer.app.open":
            self._darwin_open_app(payload)
        elif system == "Darwin" and action == "computer.app.focus":
            self._darwin_focus_app(payload)
        elif system == "Darwin":
            script = self._apple_script(action, payload)
            subprocess.run(["osascript", "-e", script], check=True)
        elif system == "Windows" and action == "computer.clipboard.read":
            return self._windows_clipboard_read()
        elif system == "Windows":
            self._windows_desktop_action(action, payload)
        else:
            return {
                "action": action,
                "supported": False,
                "platform": system,
                "reason": "Desktop actions are supported on macOS and Windows.",
            }
        result: dict[str, Any] = {"action": action, "executed": True, "platform": system, "risk": risk}
        if action in {"computer.move", "computer.click"}:
            result["target"] = {"x": int(payload.get("x", 0)), "y": int(payload.get("y", 0))}
        if action == "computer.scroll":
            result["amount"] = int(payload.get("amount", 1))
        if action == "computer.hotkey":
            result["hotkey"] = self._hotkey_parts(payload)
        if action == "computer.clipboard.write":
            result["bytes_written"] = len(str(payload.get("text") or payload.get("content") or "").encode("utf-8"))
        if action in {"computer.app.open", "computer.app.focus"}:
            result["app"] = self._app_name(payload)
        if action in {"computer.window.focus", "computer.window.bounds"}:
            result["window_id"] = str(payload.get("window_id") or payload.get("id") or "")
        return result

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

    def _darwin_scroll(self, payload: dict[str, Any]) -> None:
        amount = int(payload.get("amount", 1))
        if amount == 0:
            return
        code = (
            "import Quartz, sys\n"
            "amount = int(sys.argv[1])\n"
            "event = Quartz.CGEventCreateScrollWheelEvent(\n"
            "    None,\n"
            "    Quartz.kCGScrollEventUnitLine,\n"
            "    1,\n"
            "    amount,\n"
            ")\n"
            "Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)\n"
        )
        try:
            subprocess.run(["python3", "-c", code, str(amount)], check=True)
        except Exception as exc:
            raise RuntimeError("computer.scroll requires PyObjC Quartz on macOS") from exc

    def _darwin_hotkey_script(self, payload: dict[str, Any]) -> str:
        parts = self._hotkey_parts(payload)
        key = parts["key"]
        modifiers = []
        modifier_map = {
            "cmd": "command down",
            "command": "command down",
            "meta": "command down",
            "ctrl": "control down",
            "control": "control down",
            "alt": "option down",
            "option": "option down",
            "shift": "shift down",
        }
        for modifier in parts["modifiers"]:
            script_modifier = modifier_map.get(modifier)
            if script_modifier and script_modifier not in modifiers:
                modifiers.append(script_modifier)
        using = " using {" + ", ".join(modifiers) + "}" if modifiers else ""
        key_codes = {
            "return": 36,
            "enter": 36,
            "tab": 48,
            "space": 49,
            "delete": 51,
            "backspace": 51,
            "escape": 53,
            "esc": 53,
            "left": 123,
            "right": 124,
            "down": 125,
            "up": 126,
        }
        if re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", key):
            key_codes[key] = 121 + int(key[1:])
        if key in key_codes:
            return f'tell application "System Events" to key code {key_codes[key]}{using}'
        return f'tell application "System Events" to keystroke {json.dumps(key)}{using}'

    def _darwin_clipboard_read(self) -> dict[str, Any]:
        completed = subprocess.run(["pbpaste"], check=True, capture_output=True, text=True)
        content = completed.stdout
        return {
            "action": "computer.clipboard.read",
            "platform": "Darwin",
            "content": content,
            "bytes": len(content.encode("utf-8")),
        }

    def _darwin_clipboard_write(self, payload: dict[str, Any]) -> None:
        content = str(payload.get("text") if "text" in payload else payload.get("content") or "")
        subprocess.run(["pbcopy"], input=content, check=True, text=True)

    def _darwin_focus_window(self, payload: dict[str, Any]) -> None:
        app = self._app_name(payload)
        if not app:
            raise ValueError("computer.window.focus requires app or name on macOS")
        window_index = int(payload.get("window_index") or payload.get("index") or 1)
        script = [
            'tell application "System Events"',
            f"tell application process {json.dumps(app)}",
            "set frontmost to true",
            f"if exists window {window_index} then perform action \"AXRaise\" of window {window_index}",
            "end tell",
            "end tell",
        ]
        self._run_osascript(script)

    def _darwin_set_window_bounds(self, payload: dict[str, Any]) -> None:
        app = self._app_name(payload)
        if not app:
            raise ValueError("computer.window.bounds requires app or name on macOS")
        window_index = int(payload.get("window_index") or payload.get("index") or 1)
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))
        width = int(payload.get("width", 800))
        height = int(payload.get("height", 600))
        script = [
            'tell application "System Events"',
            f"tell application process {json.dumps(app)}",
            "set frontmost to true",
            f"set position of window {window_index} to {{{x}, {y}}}",
            f"set size of window {window_index} to {{{width}, {height}}}",
            "end tell",
            "end tell",
        ]
        self._run_osascript(script)

    def _darwin_open_app(self, payload: dict[str, Any]) -> None:
        bundle_id = str(payload.get("bundle_id") or "").strip()
        app_path = str(payload.get("path") or "").strip()
        app = self._app_name(payload)
        if bundle_id:
            subprocess.run(["open", "-b", bundle_id], check=True)
            return
        if app_path:
            subprocess.run(["open", app_path], check=True)
            return
        if not app:
            raise ValueError("computer.app.open requires app, name, bundle_id, or path")
        subprocess.run(["open", "-a", app], check=True)

    def _darwin_focus_app(self, payload: dict[str, Any]) -> None:
        app = self._app_name(payload)
        if not app:
            raise ValueError("computer.app.focus requires app or name")
        subprocess.run(["osascript", "-e", f'tell application {json.dumps(app)} to activate'], check=True)

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
        if action == "computer.move":
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
            self._run_powershell("\n".join(prelude + [f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})"]))
            return
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
        if action == "computer.hotkey":
            sequence = self._windows_hotkey_sequence(payload)
            self._run_powershell("\n".join(prelude + [f"[System.Windows.Forms.SendKeys]::SendWait('{sequence}')"]))
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
        if action == "computer.clipboard.write":
            content = str(payload.get("text") if "text" in payload else payload.get("content") or "")
            self._run_powershell("\n".join(prelude + [f"Set-Clipboard -Value {self._ps_here_string(content)}"]))
            return
        if action == "computer.window.focus":
            window_id = str(payload.get("window_id") or payload.get("id") or "").strip()
            if not window_id:
                raise ValueError("computer.window.focus requires window_id on Windows")
            script = self._windows_user32_prelude() + f"[void][RumiWindow]::SetForegroundWindow([IntPtr]{int(window_id)})"
            self._run_powershell(script)
            return
        if action == "computer.window.bounds":
            window_id = str(payload.get("window_id") or payload.get("id") or "").strip()
            if not window_id:
                raise ValueError("computer.window.bounds requires window_id on Windows")
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
            width = int(payload.get("width", 800))
            height = int(payload.get("height", 600))
            script = self._windows_user32_prelude() + f"[void][RumiWindow]::MoveWindow([IntPtr]{int(window_id)}, {x}, {y}, {width}, {height}, $true)"
            self._run_powershell(script)
            return
        if action == "computer.app.open":
            target = str(payload.get("path") or payload.get("app") or payload.get("name") or "").strip()
            if not target:
                raise ValueError("computer.app.open requires app, name, or path")
            self._run_powershell("\n".join(prelude + [f"Start-Process -FilePath {self._ps_here_string(target)}"]))
            return
        if action == "computer.app.focus":
            app = self._app_name(payload)
            if not app:
                raise ValueError("computer.app.focus requires app or name")
            self._run_powershell("\n".join(prelude + ["$shell = New-Object -ComObject WScript.Shell", f"[void]$shell.AppActivate({self._ps_here_string(app)})"]))
            return
        raise ValueError(action)

    def _windows_clipboard_read(self) -> dict[str, Any]:
        script = "Get-Clipboard -Raw"
        executable = "powershell" if shutil.which("powershell") else "pwsh"
        command = [executable, "-NoProfile"]
        if executable == "powershell":
            command.extend(["-ExecutionPolicy", "Bypass"])
        command.extend(["-Command", script])
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        content = completed.stdout
        return {
            "action": "computer.clipboard.read",
            "platform": "Windows",
            "content": content,
            "bytes": len(content.encode("utf-8")),
        }

    @staticmethod
    def _app_name(payload: dict[str, Any]) -> str:
        return str(payload.get("app") or payload.get("name") or payload.get("application") or "").strip()

    @staticmethod
    def _hotkey_parts(payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("keys"), list):
            raw_parts = [str(part).strip().lower() for part in payload.get("keys") or []]
        else:
            raw = str(payload.get("combo") or payload.get("hotkey") or payload.get("key") or "")
            raw_parts = [part.strip().lower() for part in re.split(r"[+\s]+", raw) if part.strip()]
        aliases = {
            "control": "ctrl",
            "ctl": "ctrl",
            "cmd": "cmd",
            "command": "cmd",
            "meta": "cmd",
            "win": "win",
            "windows": "win",
            "option": "alt",
            "return": "enter",
            "escape": "esc",
        }
        parts = [aliases.get(part, part) for part in raw_parts]
        modifiers = [part for part in ("ctrl", "alt", "shift", "cmd", "win") if part in parts]
        keys = [part for part in parts if part not in {"ctrl", "alt", "shift", "cmd", "win"}]
        key = keys[-1] if keys else ""
        if not key:
            raise ValueError("computer.hotkey requires combo, hotkey, key, or keys with a non-modifier key")
        return {"modifiers": modifiers, "key": key, "combo": "+".join(modifiers + [key])}

    def _windows_hotkey_sequence(self, payload: dict[str, Any]) -> str:
        parts = self._hotkey_parts(payload)
        prefix = ""
        for modifier in parts["modifiers"]:
            if modifier == "ctrl":
                prefix += "^"
            elif modifier == "alt":
                prefix += "%"
            elif modifier == "shift":
                prefix += "+"
            elif modifier == "win":
                raise ValueError("Windows-key hotkeys are not supported by SendKeys")
        return prefix + self._windows_send_key(parts["key"])

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
            "space": " ",
        }
        if re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", normalized):
            return "{" + normalized.upper() + "}"
        return key_map.get(normalized, key)

    @staticmethod
    def _ps_single(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def _ps_here_string(value: str) -> str:
        if "'@" in value:
            return "'" + value.replace("'", "''") + "'"
        return "@'\n" + value + "\n'@"

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
            "health": True,
            "permissions": True,
            "screenshot": system in {"Darwin", "Windows"},
            "display_metadata": system in {"Darwin", "Windows"},
            "windows": system in {"Darwin", "Windows"},
            "desktop_actions": system in {"Darwin", "Windows"},
            "cursor_move": system in {"Darwin", "Windows"},
            "hotkey": system in {"Darwin", "Windows"},
            "clipboard": system in {"Darwin", "Windows"},
            "app_control": system in {"Darwin", "Windows"},
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

    def _approval_required(self, action: str, payload: dict[str, Any], *, risk: dict[str, Any] | None = None) -> dict[str, Any]:
        risk = risk or classify_approval_risk(action, payload)
        approval = self._approval_store().request(
            action,
            payload,
            risk_level=str(risk.get("risk_level") or "medium"),
            reason=str(risk.get("reason") or ""),
            issue_legacy_once_token=str(risk.get("risk_level") or "") != "high",
        )
        response = {
            "action": action,
            "requires_approval": True,
            "approval_id": approval.get("approval_id"),
            "approval_expires_in_seconds": approval.get("approval_expires_in_seconds", 300),
            "approval_hint": "Approve this request server-side, then repeat the same action with payload.approval_id and payload.approval_token.",
            "risk_level": risk.get("risk_level"),
            "risk_reason": risk.get("reason"),
            "payload": approval.get("payload", payload),
        }
        if approval.get("approval_token"):
            response["approval_token"] = approval["approval_token"]
            response["approval_hint"] = "Repeat the same action with payload.approval_token after an explicit user confirmation."
        return response

    def _issue_approval(self, action: str, payload: dict[str, Any]) -> str:
        approval = self._approval_store().request(action, payload, issue_legacy_once_token=True)
        return str(approval.get("approval_token") or "")

    def _consume_approval(
        self,
        payload: dict[str, Any],
        action: str,
        expected_payload: dict[str, Any],
        *,
        risk: dict[str, Any] | None = None,
    ) -> bool:
        risk = risk or classify_approval_risk(action, expected_payload)
        return self._approval_store().consume(
            approval_id=str(payload.get("approval_id") or ""),
            approval_token=str(payload.get("approval_token") or ""),
            action=action,
            payload=expected_payload,
            allow_legacy_token=str(risk.get("risk_level") or "") != "high",
            session_id=str(payload.get("approval_session_id") or payload.get("session_id") or ""),
        )

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

    def _approval_store(self) -> ApprovalStore:
        return ApprovalStore(Path(self._approval_path))

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "approved",
                "approval_id",
                "approval_token",
                "approval_session_id",
            }
        }
