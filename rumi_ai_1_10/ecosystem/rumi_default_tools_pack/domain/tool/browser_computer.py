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
        if action in {"computer.apps", "computer.list_apps", "computer.open_apps", "computer.applications"}:
            return self._apps(payload)
        if action in {"computer.windows", "computer.list_windows"}:
            return {"action": "computer.windows", "platform": platform.system(), "windows": self._list_windows()}
        if action == "computer.select_app":
            return self._select_app(payload)
        if action in {"computer.show_app", "computer.focus_app", "computer.activate_app"}:
            return self._show_app(payload)
        if action == "computer.select_window":
            return self._select_window(payload)
        if action == "computer.screenshot":
            return self._screenshot(payload=payload, dry_run=bool(payload.get("dry_run")), yolo_mode=yolo_mode)
        if action in {"computer.move", "computer.click", "computer.drag", "computer.type", "computer.key", "computer.scroll"}:
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
        target_app = self._app_name_from_payload(payload)
        if persistent and launch_plan.get("command") and not target_app:
            command = [str(part) for part in launch_plan["command"]]
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opened_with_managed_profile = True
        else:
            opened = self._open_url_foreground(url, app_name=target_app)
            if not opened:
                return {
                    "action": "browser.open_url",
                    "url": url,
                    "opened": False,
                    "is_error": True,
                    "profile_id": profile_id,
                    "persistent": persistent,
                    **({"target_app": target_app} if target_app else {}),
                    "reason": "Opening the requested URL failed.",
                }
        sessions = self._read_sessions()
        sessions["last_url"] = url
        sessions["active_profile_id"] = profile_id
        sessions["last_opened_with_managed_profile"] = opened_with_managed_profile
        for stale_key in ("last_opened_background", "browser_target", "chrome_target"):
            sessions.pop(stale_key, None)
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
            **({"target_app": target_app} if target_app else {}),
        }

    @staticmethod
    def _open_url_foreground(url: str, *, app_name: str = "") -> bool:
        if platform.system() == "Darwin":
            try:
                command = ["open"]
                if app_name:
                    command.extend(["-a", app_name])
                command.append(url)
                subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                return False
        if app_name:
            return False
        try:
            return bool(webbrowser.open(url))
        except Exception:
            return False

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
            for key in ("target_filter", "recovery"):
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
            "notes": "Coordinates from the latest screenshot preview are accepted by default; use coordinate_space=screen for absolute display coordinates or coordinate_space=window for selected-window coordinates.",
        }
        self._remember_last_screenshot(result)
        return result

    def _context(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        state = self._computer_state()
        sessions = self._read_sessions()
        system = platform.system()
        selected_window = state.get("target_window") if isinstance(state.get("target_window"), dict) else None
        selected_app = state.get("target_app") if isinstance(state.get("target_app"), dict) else None
        if selected_window and not self._is_usable_target_window(selected_window):
            self._clear_target_window()
            selected_window = None
        running_apps = self._running_apps()
        result: dict[str, Any] = {
            "action": "computer.context",
            "platform": system,
            "active_window": self._active_window(),
            "selected_window": selected_window,
            "selected_app": selected_app,
            "open_apps": running_apps,
            "ai_cursor": state.get("ai_cursor") if isinstance(state.get("ai_cursor"), dict) else None,
            "cursor": self._cursor_position(),
            "browser_session": {
                "last_url": sessions.get("last_url"),
                "last_opened_with_managed_profile": bool(sessions.get("last_opened_with_managed_profile")),
            },
            "notes": [
                "Computer-use is app-generic and visible-screen only: use computer.apps for open/installed apps and computer.windows for visible windows.",
                "Use select_app/select_window for visible targets, then screenshot/click/type/key against the currently visible UI.",
                "computer.move and computer.click use a virtual AI cursor unless physical=true is explicitly provided.",
                "Hidden tabs and DOM/Apple Events background input are disabled; if a requested app/window is not visible, ask the user to show it or open it visibly first.",
            ],
        }
        if payload.get("include_windows", True) is not False:
            result["windows"] = self._list_windows()
        if payload.get("include_installed_apps") is True:
            result["installed_apps"] = self._installed_apps(payload)
        return result

    def _apps(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        scope = str(payload.get("scope") or payload.get("target") or "running").strip().lower()
        include_installed = payload.get("include_installed") is True or scope in {"all", "installed", "applications", "apps"}
        running_apps = self._running_apps()
        result: dict[str, Any] = {
            "action": "computer.apps",
            "platform": platform.system(),
            "scope": scope,
            "open_apps": running_apps,
            "apps": running_apps,
        }
        if include_installed:
            installed = self._installed_apps(payload)
            result["installed_apps"] = installed
            result["apps"] = installed if scope in {"installed", "applications"} else self._merge_apps(running_apps, installed)
        return result

    @staticmethod
    def _merge_apps(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in list(primary) + list(secondary):
            name = str(item.get("name") or item.get("app") or "").strip().lower()
            path = str(item.get("path") or "").strip().lower()
            key = (name, path)
            if not name or key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _running_apps(self) -> list[dict[str, Any]]:
        system = platform.system()
        if system == "Darwin":
            return self._darwin_running_apps()
        if system == "Windows":
            return self._windows_running_apps()
        return []

    def _installed_apps(self, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = payload or {}
        try:
            limit = max(1, min(1000, int(payload.get("limit", 300))))
        except Exception:
            limit = 300
        system = platform.system()
        if system == "Darwin":
            return self._darwin_installed_apps(limit=limit)
        if system == "Windows":
            return self._windows_installed_apps(limit=limit)
        return []

    def _select_app(self, payload: dict[str, Any]) -> dict[str, Any]:
        app_filter = str(
            payload.get("app")
            or payload.get("application")
            or payload.get("name")
            or payload.get("title")
            or payload.get("title_contains")
            or ""
        ).strip()
        running_apps = self._running_apps()
        selected = None
        target = str(payload.get("target") or "").strip().lower()
        if target in {"active", "front", "front_app", "active_app"} or not app_filter:
            selected = next((item for item in running_apps if item.get("active")), None)
        if selected is None and app_filter:
            selected = next((item for item in running_apps if self._app_matches_filter(item, app_filter)), None)
        installed_match = None
        if selected is None and (payload.get("include_installed") is not False):
            installed = self._installed_apps(payload)
            installed_match = next((item for item in installed if self._app_matches_filter(item, app_filter)), None)
        else:
            installed = []
        if selected is None and installed_match and (payload.get("open") is True or payload.get("launch") is True):
            launched = self._launch_app(installed_match)
            if launched:
                time.sleep(0.5)
                running_apps = self._running_apps()
                selected = next((item for item in running_apps if self._app_matches_filter(item, app_filter)), None)
        if selected is None:
            self._clear_target_app()
            return {
                "action": "computer.select_app",
                "selected": False,
                "platform": platform.system(),
                "app_filter": app_filter,
                "open_apps": running_apps,
                **({"installed_match": installed_match} if installed_match else {}),
                **({"installed_apps": installed} if payload.get("include_installed") is True else {}),
            }
        selected = self._normalize_app_record(selected)
        state = self._computer_state()
        state["target_app"] = selected
        if payload.get("focus", True) is not False:
            active_window = self._active_window_for_app(str(selected.get("name") or selected.get("app") or ""))
            if active_window is not None:
                state["target_window"] = active_window
        self._write_computer_state(state)
        if payload.get("focus", True) is not False:
            self._activate_app_name(str(selected.get("name") or selected.get("app") or ""))
            active_window = self._active_window_for_app(str(selected.get("name") or selected.get("app") or ""))
            if active_window is not None:
                state = self._computer_state()
                state["target_window"] = active_window
                self._write_computer_state(state)
        return {
            "action": "computer.select_app",
            "selected": True,
            "platform": platform.system(),
            "target_app": selected,
            "open_apps": running_apps,
        }

    def _show_app(self, payload: dict[str, Any]) -> dict[str, Any]:
        action_payload = dict(payload or {})
        action_payload["focus"] = True
        if action_payload.get("open") is not False and action_payload.get("launch") is not False:
            action_payload.setdefault("open", True)
        selected_window = self._matching_window(action_payload) if self._has_window_filter(action_payload) else None
        if selected_window is not None:
            state = self._computer_state()
            state["target_window"] = selected_window
            state["target_app"] = {"name": selected_window.get("app"), "app": selected_window.get("app"), "running": True}
            self._write_computer_state(state)
            self._focus_window(selected_window)
            time.sleep(0.2)
            return {
                "action": "computer.show_app",
                "shown": True,
                "platform": platform.system(),
                "target_window": selected_window,
                "active_window": self._active_window(),
            }
        result = self._select_app(action_payload)
        shown = bool(result.get("selected"))
        active_window = None
        if shown:
            time.sleep(0.2)
            target_app = result.get("target_app") if isinstance(result.get("target_app"), dict) else {}
            active_window = self._active_window_for_app(str(target_app.get("name") or target_app.get("app") or ""))
            if active_window is not None:
                state = self._computer_state()
                state["target_window"] = active_window
                self._write_computer_state(state)
        return {
            "action": "computer.show_app",
            "shown": shown,
            "platform": platform.system(),
            **({"target_app": result.get("target_app")} if result.get("target_app") else {}),
            **({"target_window": active_window} if active_window else {}),
            **({"open_apps": result.get("open_apps")} if result.get("open_apps") else {}),
            **({"installed_match": result.get("installed_match")} if result.get("installed_match") else {}),
            "active_window": active_window or (self._active_window() if shown else None),
            **({"reason": "No running or installed app matched the request."} if not shown else {}),
        }

    @staticmethod
    def _app_matches_filter(app: dict[str, Any], needle: str) -> bool:
        value = needle.strip().lower()
        if not value:
            return True
        haystacks = [
            str(app.get("name") or ""),
            str(app.get("app") or ""),
            str(app.get("bundle_id") or ""),
            str(app.get("path") or ""),
            str(app.get("title") or ""),
        ]
        return any(value in item.lower() for item in haystacks)

    @staticmethod
    def _normalize_app_record(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        name = str(value.get("name") or value.get("app") or value.get("process") or "").strip()
        record: dict[str, Any] = {"name": name, "app": name}
        for key in ("pid", "bundle_id", "path", "title", "source"):
            if value.get(key) not in (None, ""):
                record[key] = value.get(key)
        for key in ("active", "running", "has_windows"):
            if key in value:
                record[key] = bool(value.get(key))
        if value.get("window_count") is not None:
            try:
                record["window_count"] = int(value.get("window_count") or 0)
            except Exception:
                pass
        return record

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
        drag_marker = None
        if action == "computer.drag":
            action_payload, click_marker, drag_marker = self._resolve_drag_points(payload)
        elif action in {"computer.move", "computer.click"}:
            action_payload, click_marker = self._resolve_action_point(payload, infer_window=action == "computer.click")
        if action in {"computer.move", "computer.click", "computer.drag"} and payload.get("physical") is not True:
            self._set_ai_cursor(action_payload)
            result: dict[str, Any] = {"action": action, "executed": True, "platform": system, "virtual_cursor": True}
            if action == "computer.drag":
                result["target"] = {
                    "from": {"x": int(action_payload.get("x1", 0)), "y": int(action_payload.get("y1", 0))},
                    "to": {"x": int(action_payload.get("x2", 0)), "y": int(action_payload.get("y2", 0))},
                }
                if drag_marker:
                    result["drag_marker"] = drag_marker
            else:
                result["target"] = {"x": int(action_payload.get("x", 0)), "y": int(action_payload.get("y", 0))}
            if click_marker:
                result["marker"] = click_marker
            if action in {"computer.click", "computer.drag"} and payload.get("include_screenshot", True) is not False:
                screenshot = self._capture_action_result_screenshot(
                    action_payload,
                    click_marker,
                    action_name=action,
                    drag_marker=drag_marker,
                )
                result.update(screenshot)
            return result
        if action in {"computer.type", "computer.key", "computer.scroll"} and self._background_requested(action_payload):
            return {
                "action": action,
                "executed": False,
                "is_error": True,
                "platform": system,
                "reason": "Background computer-use is disabled. Only currently visible windows can be operated.",
                "recovery": {
                    "kind": "visible_window_required",
                    "note": "Show or focus the target app/window, then retry without background/method=background.",
                },
            }
        if action in {"computer.type", "computer.key", "computer.scroll"} and action_payload.get("focus") is False:
            return {
                "action": action,
                "executed": False,
                "is_error": True,
                "platform": system,
                "reason": "Foreground input requires focus because background input is disabled.",
                "recovery": {
                    "kind": "focus_required",
                    "note": "Use a visible selected window with focus=true or omit focus=false.",
                },
            }
        if action in {"computer.type", "computer.key", "computer.scroll"}:
            self._focus_action_target(action_payload)
        if action == "computer.drag" and payload.get("physical") is True:
            self._focus_action_target(action_payload)
        if system == "Darwin" and action == "computer.move":
            self._darwin_move_cursor(action_payload)
        elif system == "Darwin" and action == "computer.click":
            self._darwin_click(action_payload)
        elif system == "Darwin" and action == "computer.drag":
            self._darwin_drag(action_payload)
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
        if action == "computer.drag":
            result["target"] = {
                "from": {"x": int(action_payload.get("x1", 0)), "y": int(action_payload.get("y1", 0))},
                "to": {"x": int(action_payload.get("x2", 0)), "y": int(action_payload.get("y2", 0))},
            }
            if click_marker:
                result["marker"] = click_marker
            if drag_marker:
                result["drag_marker"] = drag_marker
        if action == "computer.scroll":
            result["amount"] = int(action_payload.get("amount", 1))
        if action in {"computer.click", "computer.drag"} and payload.get("include_screenshot", True) is not False:
            screenshot = self._capture_action_result_screenshot(
                action_payload,
                click_marker,
                action_name=action,
                drag_marker=drag_marker,
            )
            result.update(screenshot)
        return result

    @staticmethod
    def _background_requested(payload: dict[str, Any]) -> bool:
        if payload.get("background") is True:
            return True
        mode = str(payload.get("mode") or payload.get("method") or payload.get("driver") or "").strip().lower()
        return mode in {"background", "browser_background", "chromium_background", "chrome_background", "chrome_background_dom", "background_dom"}

    @staticmethod
    def _app_name_from_payload(payload: dict[str, Any]) -> str:
        return str(
            payload.get("app")
            or payload.get("application")
            or payload.get("browser")
            or payload.get("browser_app")
            or ""
        ).strip()

    def _focus_action_target(self, payload: dict[str, Any]) -> bool:
        if payload.get("focus") is False:
            return False
        filters = self._window_filter(payload)
        app = filters.get("app", "").lower()
        title = filters.get("title", "").lower()
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
        if app and self._activate_app_name(filters.get("app", "")):
            return True
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

    def _capture_action_result_screenshot(
        self,
        payload: dict[str, Any],
        marker: dict[str, Any] | None,
        *,
        action_name: str = "computer.click",
        drag_marker: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        path = self._artifact_root / f"click-{int(time.time() * 1000)}.png"
        capture = self._capture_screenshot(path, payload)
        if not capture.get("supported", True):
            return {}
        model_path = self._model_screenshot_copy(path)
        system = capture.get("platform", platform.system())
        result = self._screenshot_result(path, model_path, system, capture_target=capture.get("target_window"))
        result["action"] = action_name
        result["screenshot_path"] = str(path)
        result["model_image_path"] = str(model_path)
        data_url = self._image_data_url(model_path)
        if data_url:
            result["data_url"] = data_url
        if marker:
            result["click_marker"] = marker
        if drag_marker:
            result["drag_marker"] = drag_marker
        return result

    def _capture_screenshot(self, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        system = platform.system()
        target = self._capture_target(payload)
        explicit_desktop = str(payload.get("target") or payload.get("capture_target") or "").strip().lower() in {
            "primary_display",
            "all_displays",
            "screen",
            "display",
            "desktop",
        }
        if target is None and self._has_window_filter(payload) and not explicit_desktop:
            return {
                "platform": system,
                "supported": False,
                "reason": "No visible window matched the requested app/title; refusing to capture the front desktop because it would mislead the model.",
                "target_filter": self._window_filter(payload),
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
        if coordinate_space in {"model", "model_image", "preview", "screenshot_preview"} or (
            coordinate_space == "auto" and self._point_looks_like_model_coordinate(x, y, state)
        ):
            model_payload, model_marker = self._resolve_model_point(payload, x, y, state)
            if model_payload is not None:
                self._set_ai_cursor(model_payload)
                return model_payload, model_marker
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

    @staticmethod
    def _coordinate_from_payload(payload: dict[str, Any], keys: tuple[str, ...], default: Any = 0) -> int:
        for key in keys:
            if key in payload and payload.get(key) is not None:
                try:
                    return int(float(payload.get(key)))
                except Exception:
                    continue
        try:
            return int(float(default))
        except Exception:
            return 0

    def _resolve_drag_points(
        self,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
        state = self._computer_state()
        cursor = state.get("ai_cursor") if isinstance(state.get("ai_cursor"), dict) else {}
        start_x = self._coordinate_from_payload(payload, ("x1", "from_x", "start_x"), cursor.get("x", 0))
        start_y = self._coordinate_from_payload(payload, ("y1", "from_y", "start_y"), cursor.get("y", 0))
        end_x = self._coordinate_from_payload(payload, ("x2", "to_x", "end_x", "x"), start_x)
        end_y = self._coordinate_from_payload(payload, ("y2", "to_y", "end_y", "y"), start_y)

        start_payload = dict(payload)
        start_payload["x"] = start_x
        start_payload["y"] = start_y
        start_action, start_marker = self._resolve_action_point(start_payload)

        end_payload = dict(payload)
        end_payload["x"] = end_x
        end_payload["y"] = end_y
        end_action, end_marker = self._resolve_action_point(end_payload, infer_window=True)

        action_payload = dict(end_action)
        action_payload["x1"] = int(start_action.get("x", 0))
        action_payload["y1"] = int(start_action.get("y", 0))
        action_payload["x2"] = int(end_action.get("x", 0))
        action_payload["y2"] = int(end_action.get("y", 0))
        action_payload["x"] = int(end_action.get("x", 0))
        action_payload["y"] = int(end_action.get("y", 0))

        drag_marker = None
        if start_marker or end_marker:
            drag_marker = {
                "from": start_marker or {"x": start_x, "y": start_y},
                "to": end_marker or {"x": end_x, "y": end_y},
            }
        return action_payload, end_marker, drag_marker

    @staticmethod
    def _point_looks_like_model_coordinate(x: int, y: int, state: dict[str, Any]) -> bool:
        last = state.get("last_screenshot") if isinstance(state, dict) else None
        if not isinstance(last, dict):
            return False
        model_size = last.get("model_image_size") if isinstance(last.get("model_image_size"), dict) else {}
        action_space = last.get("action_coordinate_system") if isinstance(last.get("action_coordinate_system"), dict) else {}
        try:
            model_width = int(model_size.get("width", 0))
            model_height = int(model_size.get("height", 0))
            action_width = int(action_space.get("width", 0))
            action_height = int(action_space.get("height", 0))
        except Exception:
            return False
        if model_width <= 0 or model_height <= 0 or action_width <= 0 or action_height <= 0:
            return False
        if model_width >= action_width and model_height >= action_height:
            return False
        return 0 <= x <= model_width and 0 <= y <= model_height

    @staticmethod
    def _resolve_model_point(
        payload: dict[str, Any],
        x: int,
        y: int,
        state: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        last = state.get("last_screenshot") if isinstance(state, dict) else None
        if not isinstance(last, dict):
            return None, None
        model_size = last.get("model_image_size") if isinstance(last.get("model_image_size"), dict) else {}
        action_space = last.get("action_coordinate_system") if isinstance(last.get("action_coordinate_system"), dict) else {}
        try:
            model_width = int(model_size.get("width", 0))
            model_height = int(model_size.get("height", 0))
            action_x = int(action_space.get("x", 0))
            action_y = int(action_space.get("y", 0))
            action_width = int(action_space.get("width", 0))
            action_height = int(action_space.get("height", 0))
        except Exception:
            return None, None
        if model_width <= 0 or model_height <= 0 or action_width <= 0 or action_height <= 0:
            return None, None
        screen_x = action_x + round(x * action_width / model_width)
        screen_y = action_y + round(y * action_height / model_height)
        action_payload = dict(payload)
        action_payload["x"] = int(screen_x)
        action_payload["y"] = int(screen_y)
        marker = {
            "x": x,
            "y": y,
            "screen_x": int(screen_x),
            "screen_y": int(screen_y),
            "coordinate_space": "model_image",
        }
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

    def _clear_target_app(self) -> None:
        state = self._computer_state()
        if "target_app" in state:
            state.pop("target_app", None)
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

    def _remember_last_screenshot(self, result: dict[str, Any]) -> None:
        state = self._computer_state()
        remembered = {
            "updated_at": self._now_iso(),
            "image_size": result.get("image_size"),
            "model_image_size": result.get("model_image_size"),
            "action_coordinate_system": result.get("action_coordinate_system"),
            "target_window": result.get("target_window"),
        }
        state["last_screenshot"] = {key: value for key, value in remembered.items() if value not in (None, "")}
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
        filters = self._window_filter(payload)
        app = filters.get("app", "").lower()
        title = filters.get("title", "").lower()
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
                window = self._normalize_window_record(item)
                if not window or not self._is_usable_target_window(window):
                    continue
                if not self._window_matches_filter(window, app=app, title=title):
                    continue
                selected = window
                break
        if selected is None:
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
            windows = self._windows_windows()
            if windows:
                return windows
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

    def _active_window_for_app(self, app_name: str) -> dict[str, Any] | None:
        app_name = app_name.strip().lower()
        if not app_name:
            return None
        active = self._active_window()
        if active and app_name in str(active.get("app") or "").lower() and self._is_usable_target_window(active):
            return self._normalize_window_record(active)
        for item in self._list_windows():
            window = self._normalize_window_record(item)
            if (
                window
                and self._is_usable_target_window(window)
                and app_name in str(window.get("app") or "").lower()
            ):
                return window
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
        for line in (completed.stdout or "").splitlines():
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

    def _darwin_running_apps(self) -> list[dict[str, Any]]:
        script = r'''
tell application "System Events"
  set output to ""
  repeat with proc in (application processes whose background only is false)
    try
      set procName to name of proc
      set procPid to unix id of proc
      set procFront to frontmost of proc
      set winCount to count of windows of proc
      set output to output & procName & tab & procPid & tab & procFront & tab & winCount & linefeed
    end try
  end repeat
  return output
end tell
'''
        try:
            completed = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        except Exception:
            return []
        apps: list[dict[str, Any]] = []
        seen: set[str] = set()
        for line in (completed.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            name = parts[0].strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            try:
                pid = int(parts[1])
            except Exception:
                pid = None
            try:
                window_count = int(parts[3])
            except Exception:
                window_count = 0
            app = {
                "name": name,
                "app": name,
                "running": True,
                "active": parts[2].strip().lower() == "true",
                "window_count": window_count,
                "has_windows": window_count > 0,
            }
            if pid is not None:
                app["pid"] = pid
            apps.append(app)
        return apps

    @staticmethod
    def _darwin_installed_apps(*, limit: int = 300) -> list[dict[str, Any]]:
        roots = [
            Path("/Applications"),
            Path.home() / "Applications",
            Path("/System/Applications"),
        ]
        apps: list[dict[str, Any]] = []
        seen: set[str] = set()
        for root in roots:
            if not root.exists():
                continue
            try:
                candidates = sorted(root.glob("*.app"), key=lambda path: path.name.lower())
            except Exception:
                continue
            for path in candidates:
                name = path.stem.strip()
                key = str(path).lower()
                if not name or key in seen:
                    continue
                seen.add(key)
                apps.append({"name": name, "app": name, "path": str(path), "source": str(root), "running": False})
                if len(apps) >= limit:
                    return apps
        return apps

    def _activate_app_name(self, app_name: str) -> bool:
        app_name = app_name.strip()
        if not app_name:
            return False
        system = platform.system()
        if system == "Darwin":
            script = """
tell application "System Events"
  set appNeedle to %s
  repeat with candidateProc in (application processes whose background only is false)
    try
      if ((name of candidateProc) contains appNeedle) then
        set frontmost of candidateProc to true
        return "activated"
      end if
    end try
  end repeat
end tell
try
  tell application appNeedle to activate
  return "activated"
end try
return "not_found"
""" % json.dumps(app_name)
            try:
                completed = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
                return "activated" in (completed.stdout or "")
            except Exception:
                return False
        if system == "Windows":
            name = self._ps_single(app_name)
            script = "\n".join(
                [
                    "Add-Type -AssemblyName Microsoft.VisualBasic",
                    f"[void][Microsoft.VisualBasic.Interaction]::AppActivate('{name}')",
                ]
            )
            try:
                self._run_powershell(script)
                return True
            except Exception:
                return False
        return False

    def _launch_app(self, app: dict[str, Any]) -> bool:
        path = str(app.get("path") or "").strip()
        name = str(app.get("name") or app.get("app") or "").strip()
        system = platform.system()
        try:
            if system == "Darwin":
                if path:
                    subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
                if name:
                    subprocess.Popen(["open", "-a", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
            if system == "Windows" and path:
                self._run_powershell(f"Start-Process -FilePath '{self._ps_single(path)}'")
                return True
        except Exception:
            return False
        return False

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

    def _darwin_drag(self, payload: dict[str, Any]) -> None:
        x1 = int(payload.get("x1", payload.get("x", 0)))
        y1 = int(payload.get("y1", payload.get("y", 0)))
        x2 = int(payload.get("x2", payload.get("x", 0)))
        y2 = int(payload.get("y2", payload.get("y", 0)))
        button = str(payload.get("button") or "left").lower()
        button_index = 1 if button in {"right", "secondary"} else 0
        down_event = "kCGEventRightMouseDown" if button_index == 1 else "kCGEventLeftMouseDown"
        drag_event = "kCGEventRightMouseDragged" if button_index == 1 else "kCGEventLeftMouseDragged"
        up_event = "kCGEventRightMouseUp" if button_index == 1 else "kCGEventLeftMouseUp"
        code = (
            "import Quartz, time\n"
            f"start = Quartz.CGPoint({x1}, {y1})\n"
            f"end = Quartz.CGPoint({x2}, {y2})\n"
            f"down = Quartz.CGEventCreateMouseEvent(None, Quartz.{down_event}, start, {button_index})\n"
            "Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)\n"
            "time.sleep(0.05)\n"
            "steps = 8\n"
            "for index in range(1, steps + 1):\n"
            "    px = start.x + (end.x - start.x) * index / steps\n"
            "    py = start.y + (end.y - start.y) * index / steps\n"
            f"    drag = Quartz.CGEventCreateMouseEvent(None, Quartz.{drag_event}, Quartz.CGPoint(px, py), {button_index})\n"
            "    Quartz.CGEventPost(Quartz.kCGHIDEventTap, drag)\n"
            "    time.sleep(0.02)\n"
            f"up = Quartz.CGEventCreateMouseEvent(None, Quartz.{up_event}, end, {button_index})\n"
            "Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)\n"
        )
        try:
            subprocess.run(["python3", "-c", code], check=True)
        except Exception as exc:
            raise RuntimeError("computer.drag requires PyObjC Quartz on macOS") from exc

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
            modifiers = payload.get("modifiers")
            if not isinstance(modifiers, list):
                modifier = payload.get("modifier")
                modifiers = [modifier] if modifier else []
            using = self._apple_script_modifiers(modifiers)
            if isinstance(key, int):
                return f'tell application "System Events" to key code {key}{using}'
            normalized = str(key).strip().lower()
            key_codes = {
                "return": 36,
                "enter": 36,
                "tab": 48,
                "escape": 53,
                "esc": 53,
                "backspace": 51,
                "delete": 51,
                "del": 51,
                "forward_delete": 117,
                "up": 126,
                "down": 125,
                "left": 123,
                "right": 124,
                "space": 49,
            }
            if normalized in key_codes:
                return f'tell application "System Events" to key code {key_codes[normalized]}{using}'
            return f'tell application "System Events" to keystroke {json.dumps(str(key))}{using}'
        if action == "computer.scroll":
            amount = int(payload.get("amount", 1))
            return f'tell application "System Events" to scroll wheel {amount}'
        raise ValueError(action)

    @staticmethod
    def _apple_script_modifiers(modifiers: list[Any]) -> str:
        names: list[str] = []
        for item in modifiers:
            normalized = str(item or "").strip().lower()
            if normalized in {"command", "cmd", "meta", "super"}:
                names.append("command down")
            elif normalized in {"shift"}:
                names.append("shift down")
            elif normalized in {"option", "alt"}:
                names.append("option down")
            elif normalized in {"control", "ctrl"}:
                names.append("control down")
        if not names:
            return ""
        return " using {" + ", ".join(dict.fromkeys(names)) + "}"

    def _windows_running_apps(self) -> list[dict[str, Any]]:
        script = r'''
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class RumiActiveApp {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
$front = [RumiActiveApp]::GetForegroundWindow()
$items = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
  [pscustomobject]@{
    name = $_.ProcessName
    app = $_.ProcessName
    pid = $_.Id
    title = $_.MainWindowTitle
    running = $true
    active = ($_.MainWindowHandle -eq $front)
    window_count = 1
    has_windows = $true
  }
}
$items | ConvertTo-Json -Compress
'''
        try:
            return [self._normalize_app_record(item) for item in self._json_list(self._run_powershell_capture(script))]
        except Exception:
            return []

    def _windows_installed_apps(self, *, limit: int = 300) -> list[dict[str, Any]]:
        script = r'''
$ErrorActionPreference = 'SilentlyContinue'
$limit = %d
$roots = @(
  "$env:ProgramData\Microsoft\Windows\Start Menu\Programs",
  "$env:APPDATA\Microsoft\Windows\Start Menu\Programs",
  "$env:ProgramFiles",
  "${env:ProgramFiles(x86)}"
) | Where-Object { $_ -and (Test-Path $_) }
$items = @()
foreach ($root in $roots) {
  $items += Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @('.lnk', '.exe') } |
    Select-Object -First $limit |
    ForEach-Object {
      [pscustomobject]@{
        name = $_.BaseName
        app = $_.BaseName
        path = $_.FullName
        source = $root
        running = $false
      }
    }
  if ($items.Count -ge $limit) { break }
}
$items | Select-Object -First $limit | ConvertTo-Json -Compress
''' % limit
        try:
            return [self._normalize_app_record(item) for item in self._json_list(self._run_powershell_capture(script))]
        except Exception:
            return []

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
        if action == "computer.drag":
            x1 = int(payload.get("x1", payload.get("x", 0)))
            y1 = int(payload.get("y1", payload.get("y", 0)))
            x2 = int(payload.get("x2", payload.get("x", 0)))
            y2 = int(payload.get("y2", payload.get("y", 0)))
            restore_cursor = payload.get("isolate_cursor", True) is not False
            script = "\n".join(
                prelude
                + [
                    "Add-Type -TypeDefinition @'\nusing System;\nusing System.Runtime.InteropServices;\npublic class RumiMouse {\n  [DllImport(\"user32.dll\")]\n  public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);\n}\n'@",
                    "$original = [System.Windows.Forms.Cursor]::Position",
                    f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x1}, {y1})",
                    "[RumiMouse]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)",
                    f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x2}, {y2})",
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

    def _windows_windows(self) -> list[dict[str, Any]]:
        script = r'''
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class RumiWindowEnum {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
'@
$front = [RumiWindowEnum]::GetForegroundWindow()
$items = New-Object System.Collections.Generic.List[object]
$callback = [RumiWindowEnum+EnumWindowsProc]{
  param([IntPtr]$hWnd, [IntPtr]$lParam)
  if (-not [RumiWindowEnum]::IsWindowVisible($hWnd)) { return $true }
  $titleBuilder = New-Object System.Text.StringBuilder 512
  [void][RumiWindowEnum]::GetWindowText($hWnd, $titleBuilder, $titleBuilder.Capacity)
  $title = $titleBuilder.ToString()
  if ([string]::IsNullOrWhiteSpace($title)) { return $true }
  $rect = New-Object RumiWindowEnum+RECT
  if (-not [RumiWindowEnum]::GetWindowRect($hWnd, [ref]$rect)) { return $true }
  $width = $rect.Right - $rect.Left
  $height = $rect.Bottom - $rect.Top
  if ($width -le 0 -or $height -le 0) { return $true }
  [uint32]$pid = 0
  [void][RumiWindowEnum]::GetWindowThreadProcessId($hWnd, [ref]$pid)
  $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
  $items.Add([pscustomobject]@{
    app = if ($proc) { $proc.ProcessName } else { "" }
    title = $title
    x = $rect.Left
    y = $rect.Top
    width = $width
    height = $height
    active = ($hWnd -eq $front)
    window_id = $hWnd.ToInt64()
  })
  return $true
}
[void][RumiWindowEnum]::EnumWindows($callback, [IntPtr]::Zero)
$items | ConvertTo-Json -Compress
'''
        try:
            return [window for window in (self._normalize_window_record(item) for item in self._json_list(self._run_powershell_capture(script))) if window]
        except Exception:
            return []

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
    def _run_powershell_capture(script: str) -> str:
        executable = "powershell" if shutil.which("powershell") else "pwsh"
        completed = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout or ""

    @staticmethod
    def _json_list(raw: str) -> list[Any]:
        if not raw.strip():
            return []
        value = json.loads(raw)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        return []

    @staticmethod
    def _capabilities() -> dict[str, bool]:
        system = platform.system()
        return {
            "browser_open_url": True,
            "browser_persistent_profiles": True,
            "browser_cookie_management": True,
            "browser_cache_management": True,
            "screenshot": system in {"Darwin", "Windows"},
            "app_listing": system in {"Darwin", "Windows"},
            "app_selection": system in {"Darwin", "Windows"},
            "installed_app_listing": system in {"Darwin", "Windows"},
            "window_selection": system in {"Darwin", "Windows"},
            "desktop_actions": system in {"Darwin", "Windows"},
            "cursor_move": system in {"Darwin", "Windows"},
            "virtual_ai_cursor": True,
            "driver_auto_switch": system in {"Darwin", "Windows"},
            "visible_window_only": True,
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
