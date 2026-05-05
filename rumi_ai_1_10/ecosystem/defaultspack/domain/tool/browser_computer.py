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
import zlib
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
        if action in {"computer.zoom", "zoom"}:
            return self._zoom(payload)
        if action in {
            "computer.move",
            "computer.click",
            "computer.type",
            "computer.key",
            "computer.scroll",
            "computer.wait",
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
        target_context = self._prepare_target_context(payload, system=system, focus=payload.get("focus", True) is not False)
        target_bounds = self._target_capture_bounds(target_context)
        if system == "Darwin":
            command = ["screencapture", "-x"]
            if target_bounds:
                command.extend(["-R", self._region_arg(target_bounds)])
            command.append(str(path))
            subprocess.run(command, check=True)
        elif system == "Windows":
            self._windows_screenshot(path, bounds=target_bounds)
        else:
            return {
                "action": "computer.screenshot",
                "supported": False,
                "platform": system,
                "reason": "Screenshots are supported on macOS and Windows.",
            }
        quality = self._normalize_screenshot_quality(payload)
        try:
            model_path = self._model_screenshot_copy(path, quality=quality)
        except TypeError:
            model_path = self._model_screenshot_copy(path)
        data_url = ""
        try:
            mime_type = "image/jpeg" if model_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            data_url = "data:{};base64,".format(mime_type) + base64.b64encode(model_path.read_bytes()).decode("ascii")
        except Exception:
            data_url = ""
        result = self._screenshot_result(path, model_path, system, target_context=target_context)
        result["quality"] = quality
        self._attach_click_history_visual(result)
        if data_url:
            result["data_url"] = data_url
            result["visual_data_url"] = result.get("click_history_visual_data_url") or data_url
            result["model_image_path"] = str(model_path)
        self._write_screenshot_metadata(path, result)
        return result

    def _zoom(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_path = self._zoom_source_path(payload)
        if not source_path:
            return {
                "action": "computer.zoom",
                "status": "error",
                "error": {
                    "message": "zoom requires source_path or latest: true with an existing computer screenshot",
                },
            }
        if not source_path.is_file():
            return {
                "action": "computer.zoom",
                "status": "error",
                "error": {"message": f"zoom source does not exist: {source_path}"},
                "source_path": str(source_path),
            }

        try:
            image = self._read_png_pixels(source_path)
        except Exception as exc:
            return {
                "action": "computer.zoom",
                "status": "error",
                "error": {"message": str(exc)},
                "source_path": str(source_path),
            }
        source_width = int(image["width"])
        source_height = int(image["height"])
        try:
            center = self._zoom_center_in_source_image(payload, source_path, source_width, source_height)
            center_x = int(center["x"])
            center_y = int(center["y"])
            radius = int(payload.get("radius", 80))
            crop_width = int(payload.get("width") or max(radius * 2, 1))
            crop_height = int(payload.get("height") or max(radius * 2, 1))
            scale = float(payload.get("scale", 2.0))
            if crop_width <= 0 or crop_height <= 0:
                raise ValueError("zoom width and height must be positive")
            if scale <= 0:
                raise ValueError("zoom scale must be positive")
        except Exception as exc:
            return {
                "action": "computer.zoom",
                "status": "error",
                "error": {"message": str(exc)},
                "source_path": str(source_path),
            }

        left = max(min(center_x - crop_width // 2, source_width - 1), 0)
        top = max(min(center_y - crop_height // 2, source_height - 1), 0)
        right = min(left + crop_width, source_width)
        bottom = min(top + crop_height, source_height)
        left = max(right - crop_width, 0)
        top = max(bottom - crop_height, 0)
        cropped = self._crop_png_pixels(image, left, top, right, bottom)
        if scale != 1.0:
            cropped = self._scale_png_pixels(cropped, scale)

        self._artifact_root.mkdir(parents=True, exist_ok=True)
        output_path = self._artifact_root / f"zoom-{int(time.time() * 1000)}.png"
        self._write_png_pixels(output_path, cropped)
        data_url = self._image_data_url(output_path)
        crop_bounds = {"x": left, "y": top, "width": right - left, "height": bottom - top, "right": right, "bottom": bottom}
        center = {"x": center_x, "y": center_y, "coordinate_space": "source_image"}
        zoom_point = {
            "type": "point",
            "x": int(round((center_x - left) * scale)),
            "y": int(round((center_y - top) * scale)),
            "coordinate_space": "zoom_image",
            "label": "zoom",
            "source": center,
        }
        return {
            "action": "computer.zoom",
            "path": str(output_path),
            "source_path": str(source_path),
            "mime_type": "image/png",
            "data_url": data_url,
            "visual_data_url": data_url,
            "crop_bounds": crop_bounds,
            "center": center,
            "source_point": self._point_annotation(
                "zoom-source",
                int(payload.get("x", center_x)),
                int(payload.get("y", center_y)),
                coordinate_space=str(payload.get("coordinate_space") or "source_image"),
            ),
            "scale": scale,
            "image_size": {"width": cropped["width"], "height": cropped["height"]},
            "source_image_size": {"width": source_width, "height": source_height},
            "coordinate_system": {
                "origin": "top_left",
                "unit": "px",
                "space": "source_image",
                "x_range": [0, max(source_width - 1, 0)],
                "y_range": [0, max(source_height - 1, 0)],
            },
            "zoom_coordinate_system": {
                "origin": "top_left",
                "unit": "px",
                "space": "zoom_image",
                "source_crop_bounds": crop_bounds,
                "source_to_zoom_scale": {"x": scale, "y": scale},
            },
            "annotation": zoom_point,
            "overlay_points": [zoom_point],
        }

    def _zoom_center_in_source_image(
        self,
        payload: dict[str, Any],
        source_path: Path,
        source_width: int,
        source_height: int,
    ) -> dict[str, int]:
        normalized = self._normalized_point_from_payload(payload)
        if normalized:
            x = int(round(normalized["x"] * max(source_width - 1, 1) / 1000))
            y = int(round(normalized["y"] * max(source_height - 1, 1) / 1000))
        else:
            x = int(payload.get("x", source_width // 2))
            y = int(payload.get("y", source_height // 2))
        coordinate_space = str(payload.get("coordinate_space") or "source_image").strip().lower()
        if coordinate_space in {"source_image", "screenshot_image", "image", "", "normalized_1000", "normalized"}:
            return {"x": x, "y": y}
        metadata = self._screenshot_metadata_for_path(source_path) or self._latest_screenshot_metadata()
        if not metadata:
            return {"x": x, "y": y}
        if coordinate_space == "model_image":
            converted = self._model_point_to_screenshot_point(x, y, metadata)
            if converted:
                return converted
        if coordinate_space in {"target_window", "window", "local"}:
            converted = self._target_point_to_screenshot_point(x, y, metadata)
            if converted:
                return converted
        if coordinate_space in {"desktop", "action", "screen"}:
            converted = self._action_point_to_screenshot_point(x, y, metadata)
            if converted:
                return converted
        return {"x": x, "y": y}

    def _zoom_source_path(self, payload: dict[str, Any]) -> Path | None:
        raw_source = str(payload.get("source_path") or payload.get("screenshot_path") or payload.get("path") or "").strip()
        if raw_source:
            return Path(raw_source).expanduser()
        raw_model = str(payload.get("model_image_path") or "").strip()
        if raw_model:
            metadata = self._screenshot_metadata_for_path(Path(raw_model).expanduser())
            if metadata and metadata.get("path"):
                return Path(str(metadata["path"])).expanduser()
        if not bool(payload.get("latest")):
            return None
        candidates = [
            path
            for path in self._artifact_root.glob("screenshot-*.png")
            if path.is_file() and "-model" not in path.stem
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _screenshot_result(
        self,
        path: Path,
        model_path: Path,
        system: str,
        *,
        target_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"action": "computer.screenshot", "path": str(path), "mime_type": "image/png", "platform": system}
        image_size = self._image_size(path)
        model_image_size = self._image_size(model_path)
        target_context = target_context or self._desktop_target_context()
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
        target_bounds = self._valid_bounds(target_context.get("bounds"))
        if target_bounds and image_size and image_size[0] and image_size[1]:
            result["target_action_size"] = {"width": target_bounds["width"], "height": target_bounds["height"]}
            result["screenshot_to_target_scale"] = {
                "x": target_bounds["width"] / image_size[0],
                "y": target_bounds["height"] / image_size[1],
            }
            if model_image_size and model_image_size[0] and model_image_size[1]:
                result["model_to_target_scale"] = {
                    "x": target_bounds["width"] / model_image_size[0],
                    "y": target_bounds["height"] / model_image_size[1],
                }
            result["target_to_action_offset"] = {"x": target_bounds["x"], "y": target_bounds["y"]}
        cursor = self._cursor_position()
        if cursor:
            result["cursor"] = cursor
        result["target"] = target_context
        if target_context.get("origin"):
            result["screenshot_origin"] = target_context["origin"]
            result["screenshot_to_action_offset"] = target_context["origin"]
        result["cursor_move_contract"] = {
            "tool": "browser_use",
            "action": "move",
            "screen_coordinates": True,
            "coordinate_source": "screenshot",
            "notes": "Pass coordinate_space explicitly. Use coordinate_space=model_image for points selected on model_image_path, screenshot_image for path pixels, target_window for local window points, normalized_1000 for Gemini operator points shaped as [y, x] in 0..1000, and desktop/action for absolute display points. The tool converts model/screenshot/window/normalized points to desktop action coordinates.",
        }
        result["normalized_coordinate_system"] = {
            "origin": "top_left",
            "unit": "normalized",
            "space": "normalized_1000",
            "point_order": "yx",
            "x_range": [0, 1000],
            "y_range": [0, 1000],
            "example": {"point": [500, 500], "meaning": "center of the screenshot/model image"},
        }
        result["operator_point_contract"] = {
            "format": [{"point": [500, 500]}],
            "point_order": "yx",
            "coordinate_space": "normalized_1000",
            "notes": "Compatible with browser_tool_test Operator output; pass the selected item as point=[y,x].",
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

    @staticmethod
    def _normalize_screenshot_quality(payload: dict[str, Any]) -> str:
        raw = str(
            payload.get("quality")
            or payload.get("image_detail")
            or payload.get("vision_detail")
            or ""
        ).strip().lower()
        aliases = {
            "low": "compact",
            "compact": "compact",
            "standard": "standard",
            "auto": "standard",
            "high": "high_detail",
            "hi": "high_detail",
            "high_detail": "high_detail",
            "original": "high_detail",
            "full": "high_detail",
        }
        return aliases.get(raw, "standard")

    def _model_screenshot_copy(self, path: Path, *, quality: str = "standard") -> Path:
        if quality == "high_detail":
            return path
        preview_path = path.with_name(path.stem + "-model.jpg")
        if platform.system() == "Darwin":
            try:
                max_size = "640" if quality == "compact" else "1280"
                subprocess.run(
                    ["sips", "-Z", max_size, "-s", "format", "jpeg", str(path), "--out", str(preview_path)],
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
    def _screenshot_metadata_path(path: Path) -> Path:
        stem = path.stem
        if stem.endswith("-model"):
            stem = stem[:-6]
        return path.with_name(stem + ".json")

    def _write_screenshot_metadata(self, path: Path, result: dict[str, Any]) -> None:
        try:
            metadata = dict(result)
            metadata.pop("data_url", None)
            metadata.pop("visual_data_url", None)
            metadata.pop("click_history_visual_data_url", None)
            metadata["metadata_path"] = str(self._screenshot_metadata_path(path))
            self._screenshot_metadata_path(path).write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _screenshot_metadata_for_path(self, path: Path | None) -> dict[str, Any] | None:
        if path is None:
            return None
        candidates = [self._screenshot_metadata_path(path)]
        if path.suffix.lower() == ".json":
            candidates.insert(0, path)
        for candidate in candidates:
            try:
                if candidate.is_file():
                    value = json.loads(candidate.read_text(encoding="utf-8"))
                    return value if isinstance(value, dict) else None
            except Exception:
                continue
        return None

    def _latest_screenshot_metadata(self) -> dict[str, Any] | None:
        try:
            candidates = [
                path
                for path in self._artifact_root.glob("screenshot-*.json")
                if path.is_file() and "-model" not in path.stem
            ]
            if not candidates:
                return None
            return self._screenshot_metadata_for_path(max(candidates, key=lambda path: path.stat().st_mtime))
        except Exception:
            return None

    def _coordinate_reference_metadata(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        for key in ("screenshot_metadata_path", "metadata_path", "screenshot_path", "source_path", "model_image_path"):
            raw = str(payload.get(key) or "").strip()
            if raw:
                metadata = self._screenshot_metadata_for_path(Path(raw).expanduser())
                if metadata:
                    return metadata
        if payload.get("latest") is not False:
            return self._latest_screenshot_metadata()
        return None

    @staticmethod
    def _size_from_metadata(metadata: dict[str, Any], key: str) -> tuple[float, float] | None:
        value = metadata.get(key)
        if not isinstance(value, dict):
            return None
        width = value.get("width")
        height = value.get("height")
        if isinstance(width, (int, float)) and isinstance(height, (int, float)) and width > 0 and height > 0:
            return float(width), float(height)
        return None

    @staticmethod
    def _metadata_target_bounds(metadata: dict[str, Any]) -> dict[str, int] | None:
        target = metadata.get("target")
        if isinstance(target, dict):
            bounds = BrowserComputerController._valid_bounds(target.get("bounds"))
            if bounds:
                return bounds
            window = target.get("window")
            if isinstance(window, dict):
                return BrowserComputerController._valid_bounds(window.get("bounds"))
        return None

    def _model_point_to_screenshot_point(self, x: int, y: int, metadata: dict[str, Any]) -> dict[str, int] | None:
        screenshot_size = self._size_from_metadata(metadata, "image_size")
        model_size = self._size_from_metadata(metadata, "model_image_size")
        if not screenshot_size or not model_size:
            return None
        return {
            "x": int(round(float(x) * screenshot_size[0] / model_size[0])),
            "y": int(round(float(y) * screenshot_size[1] / model_size[1])),
        }

    def _target_point_to_screenshot_point(self, x: int, y: int, metadata: dict[str, Any]) -> dict[str, int] | None:
        screenshot_size = self._size_from_metadata(metadata, "image_size")
        bounds = self._metadata_target_bounds(metadata)
        if not screenshot_size or not bounds:
            return None
        return {
            "x": int(round(float(x) * screenshot_size[0] / bounds["width"])),
            "y": int(round(float(y) * screenshot_size[1] / bounds["height"])),
        }

    def _action_point_to_screenshot_point(self, x: int, y: int, metadata: dict[str, Any]) -> dict[str, int] | None:
        screenshot_size = self._size_from_metadata(metadata, "image_size")
        if not screenshot_size:
            return None
        bounds = self._metadata_target_bounds(metadata)
        if bounds:
            local_x = float(x) - float(bounds["x"])
            local_y = float(y) - float(bounds["y"])
            return self._target_point_to_screenshot_point(int(round(local_x)), int(round(local_y)), metadata)
        action_size = self._size_from_metadata(metadata, "action_coordinate_system")
        if not action_size:
            return None
        return {
            "x": int(round(float(x) * screenshot_size[0] / action_size[0])),
            "y": int(round(float(y) * screenshot_size[1] / action_size[1])),
        }

    @staticmethod
    def _image_data_url(path: Path) -> str:
        try:
            mime_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            return "data:{};base64,".format(mime_type) + base64.b64encode(path.read_bytes()).decode("ascii")
        except Exception:
            return ""

    @staticmethod
    def _read_png_pixels(path: Path) -> dict[str, Any]:
        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("zoom currently supports PNG screenshots")
        offset = 8
        width = height = bit_depth = color_type = None
        idat = bytearray()
        while offset + 8 <= len(data):
            length = int.from_bytes(data[offset : offset + 4], "big")
            chunk_type = data[offset + 4 : offset + 8]
            chunk_data = data[offset + 8 : offset + 8 + length]
            offset += 12 + length
            if chunk_type == b"IHDR":
                width, height = struct.unpack(">II", chunk_data[:8])
                bit_depth = chunk_data[8]
                color_type = chunk_data[9]
                if chunk_data[12] != 0:
                    raise ValueError("interlaced PNG screenshots are not supported")
            elif chunk_type == b"IDAT":
                idat.extend(chunk_data)
            elif chunk_type == b"IEND":
                break
        if not width or not height or bit_depth != 8 or color_type not in {0, 2, 6}:
            raise ValueError("zoom supports 8-bit grayscale, RGB, and RGBA PNG screenshots")
        channels = {0: 1, 2: 3, 6: 4}[int(color_type)]
        raw = zlib.decompress(bytes(idat))
        stride = int(width) * channels
        rows: list[bytearray] = []
        previous = bytearray(stride)
        cursor = 0
        for _ in range(int(height)):
            filter_type = raw[cursor]
            cursor += 1
            current = bytearray(raw[cursor : cursor + stride])
            cursor += stride
            for index in range(stride):
                left = current[index - channels] if index >= channels else 0
                up = previous[index]
                upper_left = previous[index - channels] if index >= channels else 0
                if filter_type == 1:
                    current[index] = (current[index] + left) & 0xFF
                elif filter_type == 2:
                    current[index] = (current[index] + up) & 0xFF
                elif filter_type == 3:
                    current[index] = (current[index] + ((left + up) // 2)) & 0xFF
                elif filter_type == 4:
                    current[index] = (current[index] + BrowserComputerController._paeth(left, up, upper_left)) & 0xFF
                elif filter_type != 0:
                    raise ValueError(f"unsupported PNG filter type: {filter_type}")
            rows.append(current)
            previous = current
        return {"width": int(width), "height": int(height), "channels": channels, "color_type": int(color_type), "rows": rows}

    @staticmethod
    def _crop_png_pixels(image: dict[str, Any], left: int, top: int, right: int, bottom: int) -> dict[str, Any]:
        channels = int(image["channels"])
        rows = [
            bytearray(row[left * channels : right * channels])
            for row in image["rows"][top:bottom]
        ]
        return {
            "width": max(right - left, 1),
            "height": max(bottom - top, 1),
            "channels": channels,
            "color_type": int(image["color_type"]),
            "rows": rows,
        }

    @staticmethod
    def _scale_png_pixels(image: dict[str, Any], scale: float) -> dict[str, Any]:
        source_width = int(image["width"])
        source_height = int(image["height"])
        channels = int(image["channels"])
        target_width = max(int(round(source_width * scale)), 1)
        target_height = max(int(round(source_height * scale)), 1)
        rows: list[bytearray] = []
        for y in range(target_height):
            source_y = min(int(y / scale), source_height - 1)
            source_row = image["rows"][source_y]
            row = bytearray(target_width * channels)
            for x in range(target_width):
                source_x = min(int(x / scale), source_width - 1)
                start = source_x * channels
                row[x * channels : (x + 1) * channels] = source_row[start : start + channels]
            rows.append(row)
        return {
            "width": target_width,
            "height": target_height,
            "channels": channels,
            "color_type": int(image["color_type"]),
            "rows": rows,
        }

    @staticmethod
    def _write_png_pixels(path: Path, image: dict[str, Any]) -> None:
        width = int(image["width"])
        height = int(image["height"])
        color_type = int(image["color_type"])
        raw = bytearray()
        for row in image["rows"]:
            raw.append(0)
            raw.extend(row)
        chunks = [
            BrowserComputerController._png_chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0),
            ),
            BrowserComputerController._png_chunk(b"IDAT", zlib.compress(bytes(raw))),
            BrowserComputerController._png_chunk(b"IEND", b""),
        ]
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"".join(chunks))

    @staticmethod
    def _png_chunk(chunk_type: bytes, chunk_data: bytes) -> bytes:
        import binascii

        crc = binascii.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        return len(chunk_data).to_bytes(4, "big") + chunk_type + chunk_data + crc.to_bytes(4, "big")

    @staticmethod
    def _paeth(left: int, up: int, upper_left: int) -> int:
        estimate = left + up - upper_left
        left_distance = abs(estimate - left)
        up_distance = abs(estimate - up)
        upper_left_distance = abs(estimate - upper_left)
        if left_distance <= up_distance and left_distance <= upper_left_distance:
            return left
        if up_distance <= upper_left_distance:
            return up
        return upper_left

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

    def _prepare_target_context(self, payload: dict[str, Any], *, system: str, focus: bool) -> dict[str, Any]:
        scope = self._target_scope(payload)
        context = self._desktop_target_context(scope=scope)
        if scope in {"desktop", "full_desktop", "all_displays"}:
            return context

        if focus:
            try:
                if scope == "window":
                    if system == "Darwin":
                        self._darwin_focus_window(payload)
                    elif system == "Windows" and str(payload.get("window_id") or payload.get("id") or "").strip():
                        self._windows_desktop_action("computer.window.focus", payload)
                elif scope in {"app", "app_window"} and self._app_name(payload):
                    if system == "Darwin":
                        self._darwin_focus_app(payload)
                    elif system == "Windows":
                        self._windows_desktop_action("computer.app.focus", payload)
                if scope in {"window", "app", "app_window"}:
                    time.sleep(0.2)
            except Exception as exc:
                context["focus_error"] = str(exc)

        window = self._window_for_target(system, payload, scope)
        if window:
            bounds = self._valid_bounds(window.get("bounds"))
            if bounds:
                context.update(
                    {
                        "scope": scope,
                        "window": window,
                        "bounds": bounds,
                        "origin": {"x": bounds["x"], "y": bounds["y"]},
                        "coordinate_space": "target_window",
                    }
                )
        return context

    @staticmethod
    def _desktop_target_context(*, scope: str = "desktop") -> dict[str, Any]:
        normalized = scope if scope in {"desktop", "full_desktop", "all_displays"} else "desktop"
        return {"scope": normalized, "coordinate_space": "desktop", "origin": {"x": 0, "y": 0}}

    def _target_scope(self, payload: dict[str, Any]) -> str:
        raw = str(
            payload.get("target")
            or payload.get("target_scope")
            or payload.get("screen_mode")
            or payload.get("mode")
            or ""
        ).strip().lower()
        aliases = {
            "desktop": "desktop",
            "full": "full_desktop",
            "full_screen": "full_desktop",
            "fullscreen": "full_desktop",
            "full_desktop": "full_desktop",
            "entire_desktop": "full_desktop",
            "all": "all_displays",
            "all_displays": "all_displays",
            "primary_display": "desktop",
            "active_window": "active_window",
            "focused_window": "active_window",
            "window": "window",
            "app": "app",
            "application": "app",
            "app_window": "app_window",
            "focused_app_window": "app_window",
            "focus_app_window": "app_window",
        }
        if raw in aliases:
            return aliases[raw]
        if payload.get("window_id") or payload.get("id") or payload.get("window_index") or payload.get("index"):
            return "window"
        if self._app_name(payload):
            return "app_window"
        return "desktop"

    def _window_for_target(self, system: str, payload: dict[str, Any], scope: str) -> dict[str, Any] | None:
        if scope in {"desktop", "full_desktop", "all_displays"}:
            return None
        if system == "Darwin":
            if scope == "window":
                app = self._app_name(payload)
                index = int(payload.get("window_index") or payload.get("index") or 1)
                if app:
                    windows = [window for window in self._darwin_windows(max(index, 1) + 10) if window.get("app") == app]
                    if len(windows) >= index:
                        return windows[index - 1]
            return self._darwin_active_window()
        if system == "Windows":
            if scope == "window":
                window_id = str(payload.get("window_id") or payload.get("id") or "").strip()
                if window_id:
                    for window in self._windows_windows(100):
                        if str(window.get("id")) == window_id:
                            return window
            return self._windows_active_window()
        return None

    @staticmethod
    def _target_capture_bounds(target_context: dict[str, Any]) -> dict[str, int] | None:
        scope = target_context.get("scope")
        if scope in {"desktop", "full_desktop", "all_displays"}:
            return None
        return BrowserComputerController._valid_bounds(target_context.get("bounds"))

    @staticmethod
    def _valid_bounds(raw: Any) -> dict[str, int] | None:
        if not isinstance(raw, dict):
            return None
        try:
            bounds = {
                "x": int(raw.get("x", 0)),
                "y": int(raw.get("y", 0)),
                "width": int(raw.get("width", 0)),
                "height": int(raw.get("height", 0)),
            }
        except Exception:
            return None
        if bounds["width"] <= 0 or bounds["height"] <= 0:
            return None
        return bounds

    @staticmethod
    def _region_arg(bounds: dict[str, int]) -> str:
        return f"{bounds['x']},{bounds['y']},{bounds['width']},{bounds['height']}"

    def _image_point_to_action_coordinates(
        self,
        payload: dict[str, Any],
        target_context: dict[str, Any],
        coordinate_space: str,
    ) -> dict[str, Any] | None:
        metadata = self._coordinate_reference_metadata(payload)
        if not metadata:
            return None
        try:
            original_x = int(payload.get("x", 0))
            original_y = int(payload.get("y", 0))
        except Exception:
            return None
        image_point = {"x": original_x, "y": original_y}
        if coordinate_space == "model_image":
            converted = self._model_point_to_screenshot_point(original_x, original_y, metadata)
            if not converted:
                return None
            image_point = converted
        elif coordinate_space not in {"screenshot_image", "source_image", "image"}:
            return None

        screenshot_size = self._size_from_metadata(metadata, "image_size")
        if not screenshot_size:
            return None

        scope = target_context.get("scope")
        bounds = self._valid_bounds(target_context.get("bounds"))
        if scope not in {"desktop", "full_desktop", "all_displays"} and bounds:
            local_x = int(round(float(image_point["x"]) * bounds["width"] / screenshot_size[0]))
            local_y = int(round(float(image_point["y"]) * bounds["height"] / screenshot_size[1]))
            origin = target_context.get("origin") if isinstance(target_context.get("origin"), dict) else {}
            action_x = int(origin.get("x", 0)) + local_x
            action_y = int(origin.get("y", 0)) + local_y
            target_window_point = self._point_annotation("target-window", local_x, local_y, coordinate_space="target_window")
        else:
            action_size = self._size_from_metadata(metadata, "action_coordinate_system")
            if not action_size:
                action_system = self._action_coordinate_system(platform.system(), (int(screenshot_size[0]), int(screenshot_size[1])))
                action_size = (
                    float(action_system.get("width", screenshot_size[0])),
                    float(action_system.get("height", screenshot_size[1])),
                ) if action_system else screenshot_size
            action_x = int(round(float(image_point["x"]) * action_size[0] / screenshot_size[0]))
            action_y = int(round(float(image_point["y"]) * action_size[1] / screenshot_size[1]))
            target_window_point = None

        source_space = "screenshot_image" if coordinate_space != "model_image" else "model_image"
        source_point = self._point_annotation("source", original_x, original_y, coordinate_space=source_space)
        screenshot_point = self._point_annotation("screenshot", image_point["x"], image_point["y"], coordinate_space="screenshot_image")
        transform = {
            "input": source_point,
            "screenshot_point": screenshot_point,
            "action_point": self._point_annotation("action", action_x, action_y, coordinate_space="action"),
            "metadata_path": metadata.get("metadata_path"),
            "source_path": metadata.get("path"),
        }
        if target_window_point:
            transform["target_window_point"] = target_window_point
        return {
            "x": action_x,
            "y": action_y,
            "local_target": {"x": target_window_point["x"], "y": target_window_point["y"]} if target_window_point else None,
            "transform": transform,
        }

    @staticmethod
    def _normalized_point_from_payload(payload: dict[str, Any]) -> dict[str, int] | None:
        raw_point = payload.get("normalized_point")
        if raw_point is None:
            raw_point = payload.get("point")
        if raw_point is None and isinstance(payload.get("points"), list) and payload.get("points"):
            first = payload.get("points")[0]
            raw_point = first.get("point") if isinstance(first, dict) and "point" in first else first

        point_order = str(payload.get("point_order") or "yx").strip().lower()
        try:
            if isinstance(raw_point, dict):
                if "point" in raw_point:
                    nested_payload = dict(payload)
                    nested_payload["point"] = raw_point.get("point")
                    return BrowserComputerController._normalized_point_from_payload(nested_payload)
                x = float(raw_point.get("x"))
                y = float(raw_point.get("y"))
            elif isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2:
                first = float(raw_point[0])
                second = float(raw_point[1])
                if point_order in {"xy", "x,y"}:
                    x, y = first, second
                else:
                    y, x = first, second
            elif payload.get("coordinate_space") in {"normalized", "normalized_1000"} and "x" in payload and "y" in payload:
                x = float(payload.get("x"))
                y = float(payload.get("y"))
            else:
                return None
        except Exception:
            return None
        if x < 0 or y < 0 or x > 1000 or y > 1000:
            return None
        return {"x": int(round(x)), "y": int(round(y))}

    def _payload_with_normalized_point(
        self,
        payload: dict[str, Any],
        target_context: dict[str, Any],
    ) -> dict[str, Any]:
        point = self._normalized_point_from_payload(payload)
        if not point:
            return dict(payload)
        adjusted = dict(payload)
        adjusted["_normalized_point"] = self._point_annotation(
            "normalized",
            point["x"],
            point["y"],
            coordinate_space="normalized_1000",
        )

        metadata = self._coordinate_reference_metadata(payload)
        screenshot_size = self._size_from_metadata(metadata, "image_size") if metadata else None
        if screenshot_size:
            adjusted["x"] = int(round(point["x"] * screenshot_size[0] / 1000))
            adjusted["y"] = int(round(point["y"] * screenshot_size[1] / 1000))
            adjusted["coordinate_space"] = "screenshot_image"
            return adjusted

        bounds = self._valid_bounds(target_context.get("bounds"))
        if bounds:
            adjusted["x"] = int(round(point["x"] * bounds["width"] / 1000))
            adjusted["y"] = int(round(point["y"] * bounds["height"] / 1000))
            adjusted["coordinate_space"] = "target_window"
            return adjusted

        action_size = self._size_from_metadata(metadata, "action_coordinate_system") if metadata else None
        if action_size:
            adjusted["x"] = int(round(point["x"] * action_size[0] / 1000))
            adjusted["y"] = int(round(point["y"] * action_size[1] / 1000))
            adjusted["coordinate_space"] = "action"
        return adjusted

    def _infer_image_coordinate_space(self, payload: dict[str, Any]) -> str:
        metadata = self._coordinate_reference_metadata(payload)
        if not metadata:
            return ""
        try:
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
        except Exception:
            return ""
        image_size = self._size_from_metadata(metadata, "image_size")
        action_size = self._size_from_metadata(metadata, "action_coordinate_system")
        if not image_size or not action_size:
            return ""
        image_width, image_height = image_size
        action_width, action_height = action_size
        if x < 0 or y < 0 or x > image_width or y > image_height:
            return ""
        # Models often emit coordinates in the screenshot they just saw. On
        # Retina displays those values can be outside the desktop action space,
        # which is a strong signal that conversion is needed.
        if x > action_width or y > action_height:
            return "screenshot_image"
        return ""

    def _payload_with_target_coordinates(
        self,
        action: str,
        payload: dict[str, Any],
        *,
        system: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if action not in {"computer.move", "computer.click"}:
            return dict(payload), self._prepare_target_context(payload, system=system, focus=True)
        target_context = self._prepare_target_context(payload, system=system, focus=True)
        adjusted = self._payload_with_normalized_point(payload, target_context)
        scope = target_context.get("scope")
        coordinate_space = str(adjusted.get("coordinate_space") or adjusted.get("coordinates") or "").strip().lower()
        if not coordinate_space:
            coordinate_space = self._infer_image_coordinate_space(adjusted)
        if coordinate_space in {"model_image", "screenshot_image", "source_image", "image"}:
            converted = self._image_point_to_action_coordinates(adjusted, target_context, coordinate_space)
            if converted:
                adjusted["x"] = converted["x"]
                adjusted["y"] = converted["y"]
                if converted.get("local_target"):
                    adjusted["_target_local_point"] = converted["local_target"]
                adjusted["_coordinate_transform"] = converted["transform"]
                if "_normalized_point" in adjusted:
                    adjusted["_coordinate_transform"]["normalized_point"] = adjusted["_normalized_point"]
                return adjusted, target_context
        if scope not in {"desktop", "full_desktop", "all_displays"} and coordinate_space not in {"desktop", "action", "screen"}:
            origin = target_context.get("origin") if isinstance(target_context.get("origin"), dict) else {}
            adjusted["x"] = int(payload.get("x", 0)) + int(origin.get("x", 0))
            adjusted["y"] = int(payload.get("y", 0)) + int(origin.get("y", 0))
            adjusted["_target_local_point"] = {"x": int(payload.get("x", 0)), "y": int(payload.get("y", 0))}
        return adjusted, target_context

    def _desktop_action(self, action: str, payload: dict[str, Any], *, yolo_mode: bool) -> dict[str, Any]:
        dry_run = bool(payload.get("dry_run"))
        approval_payload = self._safe_payload(payload)
        risk = classify_approval_risk(action, approval_payload)
        system = platform.system()
        action_payload = dict(payload)
        target_context: dict[str, Any] | None = None
        if dry_run:
            result = {"action": action, "dry_run": True, "requires_approval": False, "risk": risk, "payload": approval_payload}
            if action in {"computer.move", "computer.click"}:
                result.update(self._action_point_metadata(action, action_payload))
            return result
        if risk.get("approval_required") and not (yolo_mode or self._consume_approval(payload, action, approval_payload, risk=risk)):
            return self._approval_required(action, approval_payload, risk=risk)
        if action in {
            "computer.move",
            "computer.click",
            "computer.type",
            "computer.key",
            "computer.hotkey",
            "computer.scroll",
        }:
            action_payload, target_context = self._payload_with_target_coordinates(action, payload, system=system)
        if action == "computer.scroll":
            action_payload = self._payload_with_scroll_direction(action_payload)
        if action == "computer.wait":
            time.sleep(max(float(payload.get("seconds") or payload.get("duration") or 1), 0.0))
        elif system == "Darwin" and action == "computer.move":
            self._darwin_move_cursor(action_payload)
        elif system == "Darwin" and action == "computer.click":
            self._darwin_click(action_payload)
        elif system == "Darwin" and action == "computer.type":
            self._darwin_type(action_payload)
        elif system == "Darwin" and action == "computer.key":
            self._darwin_key(action_payload)
        elif system == "Darwin" and action == "computer.scroll":
            self._darwin_scroll(action_payload)
        elif system == "Darwin" and action == "computer.hotkey":
            self._darwin_hotkey(action_payload)
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
            script = self._apple_script(action, action_payload)
            subprocess.run(["osascript", "-e", script], check=True)
        elif system == "Windows" and action == "computer.clipboard.read":
            return self._windows_clipboard_read()
        elif system == "Windows":
            self._windows_desktop_action(action, action_payload)
        else:
            return {
                "action": action,
                "supported": False,
                "platform": system,
                "reason": "Desktop actions are supported on macOS and Windows.",
            }
        result: dict[str, Any] = {"action": action, "executed": True, "platform": system, "risk": risk}
        if action in {"computer.move", "computer.click"}:
            result["target"] = {"x": int(action_payload.get("x", 0)), "y": int(action_payload.get("y", 0))}
            if "_target_local_point" in action_payload:
                result["local_target"] = action_payload["_target_local_point"]
            result.update(self._action_point_metadata(action, action_payload))
            if "_coordinate_transform" in action_payload:
                result["coordinate_transform"] = action_payload["_coordinate_transform"]
                result["display_overlay_points"] = [
                    point
                    for point in (
                        action_payload["_coordinate_transform"].get("normalized_point"),
                        action_payload["_coordinate_transform"].get("input"),
                        action_payload["_coordinate_transform"].get("screenshot_point"),
                        action_payload["_coordinate_transform"].get("target_window_point"),
                    )
                    if isinstance(point, dict)
                ]
            self._record_click_history(action, action_payload, result)
        if target_context:
            result["target_context"] = target_context
        if action == "computer.wait":
            result["seconds"] = max(float(payload.get("seconds") or payload.get("duration") or 1), 0.0)
        if action == "computer.scroll":
            result["amount"] = int(action_payload.get("amount", 1))
        if action == "computer.hotkey":
            result["hotkey"] = self._hotkey_parts(action_payload)
        if action == "computer.clipboard.write":
            result["bytes_written"] = len(str(payload.get("text") or payload.get("content") or "").encode("utf-8"))
        if action in {"computer.app.open", "computer.app.focus"}:
            result["app"] = self._app_name(payload)
        if action in {"computer.window.focus", "computer.window.bounds"}:
            result["window_id"] = str(payload.get("window_id") or payload.get("id") or "")
        return result

    @staticmethod
    def _action_point_metadata(action: str, payload: dict[str, Any]) -> dict[str, Any]:
        label = "click" if action == "computer.click" else "move"
        point = BrowserComputerController._point_annotation(label, int(payload.get("x", 0)), int(payload.get("y", 0)))
        return {"annotation": point, "overlay_points": [point]}

    @staticmethod
    def _payload_with_scroll_direction(payload: dict[str, Any]) -> dict[str, Any]:
        adjusted = dict(payload)
        direction = str(adjusted.get("direction") or "").strip().lower()
        if not direction:
            return adjusted
        amount = abs(int(adjusted.get("amount") or 3))
        if direction in {"down", "right"}:
            adjusted["amount"] = -amount
        elif direction in {"up", "left"}:
            adjusted["amount"] = amount
        return adjusted

    def _click_history_path(self) -> Path:
        return self._artifact_root / "click_history.json"

    def _read_click_history(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self._click_history_path().read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except Exception:
            return []

    def _write_click_history(self, history: list[dict[str, Any]]) -> None:
        try:
            self._artifact_root.mkdir(parents=True, exist_ok=True)
            self._click_history_path().write_text(json.dumps(history[-5:], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _record_click_history(self, action: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
        if action != "computer.click":
            return
        point = result.get("annotation") if isinstance(result.get("annotation"), dict) else None
        points = [point] if point else []
        for candidate in result.get("display_overlay_points") or []:
            if isinstance(candidate, dict):
                points.append(candidate)
        record = {
            "ts": self._now_iso(),
            "action": action,
            "target": result.get("target"),
            "local_target": result.get("local_target"),
            "points": points,
            "metadata_path": (
                result.get("coordinate_transform", {}).get("metadata_path")
                if isinstance(result.get("coordinate_transform"), dict)
                else None
            ),
        }
        history = self._read_click_history()
        history.append(record)
        self._write_click_history(history)

    def _attach_click_history_visual(self, screenshot_result: dict[str, Any]) -> None:
        path = Path(str(screenshot_result.get("path") or ""))
        if not path.is_file():
            return
        history = self._read_click_history()
        if not history:
            return
        try:
            image = self._read_png_pixels(path)
        except Exception:
            return
        metadata = dict(screenshot_result)
        overlay_points: list[dict[str, Any]] = []
        for index, record in enumerate(history[-5:], start=1):
            point = self._history_point_for_screenshot(record, metadata)
            if not point:
                continue
            point["label"] = f"click-{index}"
            overlay_points.append(point)
            self._draw_point_on_png(image, point["x"], point["y"], radius=7, color=(220, 38, 38, 255), outline=(255, 255, 255, 255))
        if not overlay_points:
            return
        visual_path = path.with_name(path.stem + "-clicks.png")
        self._write_png_pixels(visual_path, image)
        screenshot_result["click_history_path"] = str(self._click_history_path())
        screenshot_result["click_history_visual_path"] = str(visual_path)
        screenshot_result["click_history_overlay_points"] = overlay_points
        screenshot_result["click_history_visual_data_url"] = self._image_data_url(visual_path)

    def _history_point_for_screenshot(self, record: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any] | None:
        candidates = record.get("points") if isinstance(record.get("points"), list) else []
        preferred_spaces = ("screenshot_image", "source_image", "target_window", "action", "normalized_1000")
        for space in preferred_spaces:
            for point in candidates:
                if not isinstance(point, dict) or str(point.get("coordinate_space")) != space:
                    continue
                converted = self._point_to_screenshot_space(point, metadata)
                if converted:
                    return converted
        target = record.get("target") if isinstance(record.get("target"), dict) else None
        if target:
            return self._point_to_screenshot_space(self._point_annotation("click", target.get("x", 0), target.get("y", 0)), metadata)
        return None

    def _point_to_screenshot_space(self, point: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any] | None:
        try:
            x = int(point.get("x", 0))
            y = int(point.get("y", 0))
        except Exception:
            return None
        space = str(point.get("coordinate_space") or "action")
        screenshot_size = self._size_from_metadata(metadata, "image_size")
        if not screenshot_size:
            return None
        if space in {"screenshot_image", "source_image", "image"}:
            sx, sy = x, y
        elif space == "model_image":
            converted = self._model_point_to_screenshot_point(x, y, metadata)
            if not converted:
                return None
            sx, sy = converted["x"], converted["y"]
        elif space == "target_window":
            converted = self._target_point_to_screenshot_point(x, y, metadata)
            if not converted:
                return None
            sx, sy = converted["x"], converted["y"]
        elif space in {"action", "desktop", "screen"}:
            converted = self._action_point_to_screenshot_point(x, y, metadata)
            if not converted:
                return None
            sx, sy = converted["x"], converted["y"]
        elif space in {"normalized_1000", "normalized"}:
            sx = int(round(x * screenshot_size[0] / 1000))
            sy = int(round(y * screenshot_size[1] / 1000))
        else:
            return None
        width, height = int(screenshot_size[0]), int(screenshot_size[1])
        if sx < 0 or sy < 0 or sx >= width or sy >= height:
            return None
        return self._point_annotation(str(point.get("label") or "click"), sx, sy, coordinate_space="screenshot_image")

    @staticmethod
    def _draw_point_on_png(
        image: dict[str, Any],
        x: int,
        y: int,
        *,
        radius: int,
        color: tuple[int, int, int, int],
        outline: tuple[int, int, int, int],
    ) -> None:
        width = int(image["width"])
        height = int(image["height"])
        channels = int(image["channels"])
        outer = radius + 2
        for py in range(max(y - outer, 0), min(y + outer + 1, height)):
            for px in range(max(x - outer, 0), min(x + outer + 1, width)):
                distance_sq = (px - x) * (px - x) + (py - y) * (py - y)
                if distance_sq > outer * outer:
                    continue
                rgba = outline if distance_sq > radius * radius else color
                offset = px * channels
                row = image["rows"][py]
                if channels == 1:
                    row[offset] = int((rgba[0] + rgba[1] + rgba[2]) / 3)
                elif channels == 3:
                    row[offset : offset + 3] = bytes(rgba[:3])
                else:
                    row[offset : offset + 4] = bytes(rgba)

    @staticmethod
    def _point_annotation(label: str, x: int, y: int, *, coordinate_space: str = "action") -> dict[str, Any]:
        return {
            "type": "point",
            "x": int(x),
            "y": int(y),
            "coordinate_space": coordinate_space,
            "label": label,
        }

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
        cliclick = shutil.which("cliclick")
        if cliclick:
            subprocess.run([cliclick, f"c:{x},{y}"], check=True)
            return
        swift = shutil.which("swift")
        if swift:
            code = (
                "import CoreGraphics\n"
                "import Darwin\n"
                "let x = Double(CommandLine.arguments[1])!\n"
                "let y = Double(CommandLine.arguments[2])!\n"
                "let point = CGPoint(x: x, y: y)\n"
                "CGWarpMouseCursorPosition(point)\n"
                "let down = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left)\n"
                "down?.post(tap: .cghidEventTap)\n"
                "usleep(80000)\n"
                "let up = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left)\n"
                "up?.post(tap: .cghidEventTap)\n"
            )
            subprocess.run([swift, "-e", code, str(x), str(y)], check=True)
            return
        script = self._apple_script("computer.click", payload)
        subprocess.run(["osascript", "-e", script], check=True)

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

    def _darwin_type(self, payload: dict[str, Any]) -> None:
        text = str(payload.get("text", ""))
        if text:
            self._darwin_paste_text(text)
            return
        script = self._apple_script("computer.type", payload)
        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
            return
        except subprocess.CalledProcessError:
            # System Events often rejects non-ASCII keystrokes or missing Automation
            # permission. Clipboard paste keeps Japanese text intact and uses the
            # same CoreGraphics fallback as click/move.
            self._darwin_paste_text(text)

    def _darwin_key(self, payload: dict[str, Any]) -> None:
        script = self._apple_script("computer.key", payload)
        try:
            subprocess.run(["osascript", "-e", script], check=True)
        except subprocess.CalledProcessError:
            key = str(payload.get("key", "return")).strip().lower()
            self._darwin_post_key(key)

    def _darwin_hotkey(self, payload: dict[str, Any]) -> None:
        try:
            subprocess.run(["osascript", "-e", self._darwin_hotkey_script(payload)], check=True)
        except subprocess.CalledProcessError:
            parts = self._hotkey_parts(payload)
            self._darwin_post_key(parts["key"], modifiers=parts["modifiers"])

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

    def _darwin_paste_text(self, text: str) -> None:
        try:
            old_clipboard = subprocess.run(["pbpaste"], check=True, capture_output=True, text=True).stdout
        except Exception:
            old_clipboard = None
        subprocess.run(["pbcopy"], input=str(text), check=True, text=True)
        self._darwin_post_key("v", modifiers=["cmd"])
        time.sleep(0.2)
        if old_clipboard is not None:
            try:
                subprocess.run(["pbcopy"], input=old_clipboard, check=True, text=True)
            except Exception:
                pass

    def _darwin_post_key(self, key: str, modifiers: list[str] | tuple[str, ...] | None = None) -> None:
        key_name = str(key or "").strip().lower()
        key_codes = {
            "a": 0,
            "s": 1,
            "d": 2,
            "f": 3,
            "h": 4,
            "g": 5,
            "z": 6,
            "x": 7,
            "c": 8,
            "v": 9,
            "b": 11,
            "q": 12,
            "w": 13,
            "e": 14,
            "r": 15,
            "y": 16,
            "t": 17,
            "1": 18,
            "2": 19,
            "3": 20,
            "4": 21,
            "6": 22,
            "5": 23,
            "=": 24,
            "9": 25,
            "7": 26,
            "-": 27,
            "8": 28,
            "0": 29,
            "]": 30,
            "o": 31,
            "u": 32,
            "[": 33,
            "i": 34,
            "p": 35,
            "return": 36,
            "enter": 36,
            "l": 37,
            "j": 38,
            "'": 39,
            "k": 40,
            ";": 41,
            "\\": 42,
            ",": 43,
            "/": 44,
            "n": 45,
            "m": 46,
            ".": 47,
            "tab": 48,
            "space": 49,
            "`": 50,
            "delete": 51,
            "backspace": 51,
            "escape": 53,
            "esc": 53,
            "left": 123,
            "right": 124,
            "down": 125,
            "up": 126,
        }
        if key_name not in key_codes:
            raise RuntimeError(f"Unsupported macOS key fallback: {key_name}")
        flag_names = {str(item).strip().lower() for item in (modifiers or [])}
        flags: list[str] = []
        flag_map = {
            "cmd": "maskCommand",
            "command": "maskCommand",
            "meta": "maskCommand",
            "ctrl": "maskControl",
            "control": "maskControl",
            "alt": "maskAlternate",
            "option": "maskAlternate",
            "shift": "maskShift",
        }
        for name in sorted(flag_names):
            flag = flag_map.get(name)
            if flag and flag not in flags:
                flags.append(flag)
        flags_expr = "[]"
        if flags:
            flags_expr = "CGEventFlags([" + ", ".join("." + flag for flag in flags) + "])"
        swift = f"""
import CoreGraphics
import Foundation
let source = CGEventSource(stateID: .hidSystemState)
let flags: CGEventFlags = {flags_expr}
let keyCode = CGKeyCode({key_codes[key_name]})
if let down = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: true) {{
    down.flags = flags
    down.post(tap: .cghidEventTap)
}}
Thread.sleep(forTimeInterval: 0.03)
if let up = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: false) {{
    up.flags = flags
    up.post(tap: .cghidEventTap)
}}
"""
        subprocess.run(["swift", "-e", swift], check=True)

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
            normalized = str(key).strip().lower()
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
            if normalized in key_codes:
                return f'tell application "System Events" to key code {key_codes[normalized]}'
            return f'tell application "System Events" to keystroke {json.dumps(str(key))}'
        raise ValueError(action)

    def _windows_screenshot(self, path: Path, *, bounds: dict[str, int] | None = None) -> None:
        escaped = self._ps_single(str(path))
        if bounds:
            bounds_script = [
                f"$bounds = New-Object System.Drawing.Rectangle({bounds['x']}, {bounds['y']}, {bounds['width']}, {bounds['height']})",
                "$source = New-Object System.Drawing.Point($bounds.X, $bounds.Y)",
            ]
        else:
            bounds_script = [
                "$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds",
                "$source = $bounds.Location",
            ]
        script = "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "Add-Type -AssemblyName System.Windows.Forms",
                "Add-Type -AssemblyName System.Drawing",
                *bounds_script,
                "$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height",
                "$graphics = [System.Drawing.Graphics]::FromImage($bitmap)",
                "$graphics.CopyFromScreen($source, [System.Drawing.Point]::Empty, $bounds.Size)",
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
        shortcut = str(payload.get("shortcut") or "").strip().lower()
        shortcuts = {
            "new_tab": ["cmd", "t"],
            "close_tab": ["cmd", "w"],
            "refresh": ["cmd", "r"],
            "reload": ["cmd", "r"],
            "select_all": ["cmd", "a"],
            "copy": ["cmd", "c"],
            "paste": ["cmd", "v"],
        }
        if shortcut in shortcuts:
            raw_parts = shortcuts[shortcut]
        elif isinstance(payload.get("keys"), list):
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
