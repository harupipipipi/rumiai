from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_MUTATING_ACTIONS = {
    "browser.open_url",
    "browser.select_client",
    "browser.select_tab",
    "computer.select_app",
    "computer.show_app",
    "computer.focus_app",
    "computer.activate_app",
    "computer.select_window",
    "computer.click",
    "computer.drag",
    "computer.type",
    "computer.key",
    "computer.scroll",
    "page.navigate",
    "page.click",
    "page.type",
    "page.press",
    "page.scroll",
}

_DOM_ACTIONS = {
    "page.snapshot",
    "page.extract",
}

_SNAPSHOT_ACTIONS = {
    "browser.session",
    "browser.clients",
    "browser.select_client",
    "browser.tabs",
    "browser.select_tab",
    "computer.context",
    "computer.state",
    "computer.app_context",
    "computer.windows",
    "computer.list_windows",
    "computer.select_window",
    "computer.select_app",
    "computer.show_app",
    "computer.focus_app",
    "computer.activate_app",
}


@dataclass(frozen=True)
class BrowserStateLimits:
    max_events: int = 6
    max_screenshots: int = 2
    max_windows: int = 12
    max_tabs: int = 12
    max_clients: int = 6
    max_dom_nodes: int = 200
    max_dom_attributes: int = 12
    max_string_length: int = 2000
    max_dom_text_length: int = 400


@dataclass(frozen=True)
class BrowserStateEmission:
    events: list[dict[str, Any]]
    state_revision: int


class BrowserStateNormalizer:
    """Emit canonical browser-state events from browser/computer tool results."""

    def __init__(
        self,
        *,
        state_revision: int = 0,
        limits: BrowserStateLimits | None = None,
    ) -> None:
        self._state_revision = max(int(state_revision or 0), 0)
        self._limits = limits or BrowserStateLimits()

    @property
    def state_revision(self) -> int:
        return self._state_revision

    def emit_from_tool_result(
        self,
        tool_name: str,
        result: Any,
        *,
        tool_call_id: str | None = None,
        action: str | None = None,
        timestamp: Any = None,
    ) -> BrowserStateEmission:
        roots = self._result_roots(result)
        resolved_action = self._clean_string(action)
        if not resolved_action:
            for root in roots:
                resolved_action = self._clean_string(root.get("action"))
                if resolved_action:
                    break
        events: list[dict[str, Any]] = []
        tool_name = self._clean_string(tool_name)
        tool_call_id = self._clean_string(tool_call_id)
        if not self._should_emit_browser_state(tool_name, resolved_action):
            return BrowserStateEmission(events=events, state_revision=self._state_revision)

        if self._should_emit_invalidation(resolved_action, roots):
            self._append_event(
                events,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                action=resolved_action,
                timestamp=timestamp,
                kind="invalidated",
                payload_key="invalidated",
                payload=self._build_invalidation_payload(resolved_action, roots),
            )

        snapshot = self._extract_snapshot(roots, resolved_action)
        if snapshot is not None:
            self._append_event(
                events,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                action=resolved_action,
                timestamp=timestamp,
                kind="snapshot",
                payload_key="snapshot",
                payload=snapshot,
            )

        dom_snapshot = self._extract_dom_snapshot(roots, resolved_action)
        if dom_snapshot is not None:
            self._append_event(
                events,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                action=resolved_action,
                timestamp=timestamp,
                kind="dom_snapshot",
                payload_key="dom_snapshot",
                payload=dom_snapshot,
            )

        for screenshot in self._extract_screenshots(roots, resolved_action):
            if len(events) >= self._limits.max_events:
                break
            self._append_event(
                events,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                action=resolved_action,
                timestamp=timestamp,
                kind="screenshot",
                payload_key="screenshot",
                payload=screenshot,
            )

        return BrowserStateEmission(events=events, state_revision=self._state_revision)

    def _should_emit_browser_state(self, tool_name: str, action: str) -> bool:
        normalized_tool = self._clean_string(tool_name).replace("-", "_")
        if normalized_tool.startswith("browser_") or normalized_tool.startswith("computer_"):
            return True
        return action in _MUTATING_ACTIONS or action in _DOM_ACTIONS or action in _SNAPSHOT_ACTIONS

    def _append_event(
        self,
        events: list[dict[str, Any]],
        *,
        tool_name: str,
        tool_call_id: str,
        action: str,
        timestamp: Any,
        kind: str,
        payload_key: str,
        payload: dict[str, Any] | None,
    ) -> None:
        if payload is None or len(events) >= self._limits.max_events:
            return
        self._state_revision += 1
        event: dict[str, Any] = {
            "type": "browser_state",
            "event": kind,
            "state_revision": self._state_revision,
            payload_key: payload,
        }
        if tool_name:
            event["tool_name"] = tool_name
        if tool_call_id:
            event["tool_call_id"] = tool_call_id
        if action:
            event["action"] = action
        if timestamp is not None:
            event["timestamp"] = timestamp
        events.append(event)

    @staticmethod
    def _result_roots(result: Any) -> list[dict[str, Any]]:
        roots: list[dict[str, Any]] = []
        seen: set[int] = set()

        def add(value: Any) -> None:
            if not isinstance(value, dict):
                return
            marker = id(value)
            if marker in seen:
                return
            seen.add(marker)
            roots.append(value)

        if isinstance(result, dict) and isinstance(result.get("data"), dict):
            data = result.get("data")
            add(data)
            if isinstance(data.get("widget"), dict):
                add(data.get("widget"))
            add(result)
        else:
            add(result)
            if isinstance(result, dict) and isinstance(result.get("widget"), dict):
                add(result.get("widget"))
        if isinstance(result, dict):
            for key in ("result", "output", "artifact", "capture"):
                add(result.get(key))
        return roots

    def _should_emit_invalidation(self, action: str, roots: list[dict[str, Any]]) -> bool:
        if action not in _MUTATING_ACTIONS or not roots:
            return False
        primary = roots[0]
        if self._truthy(primary.get("dry_run")) or self._truthy(primary.get("is_error")):
            return False
        if primary.get("ok") is False:
            return False
        if action == "browser.open_url":
            return primary.get("opened") is not False
        if action.startswith("computer.") and "executed" in primary:
            return bool(primary.get("executed"))
        return True

    def _build_invalidation_payload(self, action: str, roots: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reason": "tool_result_completed",
            "scope": self._invalidation_scope(action),
        }
        url = self._first_string(roots, "url")
        if not url and action == "browser.open_url":
            url = self._first_nested_string(roots, "launch", "url")
        if url:
            payload["url"] = url
        title = self._first_string(roots, "title")
        if title:
            payload["title"] = title
        window = self._first_window(
            roots,
            "target_window",
            "selected_window",
            "active_window",
            "window",
        )
        if window is not None:
            payload["window"] = window
        tab_id = self._first_int(roots, "tab_id", "active_tab_id")
        if tab_id is not None:
            payload["tab_id"] = tab_id
        return payload

    @staticmethod
    def _invalidation_scope(action: str) -> str:
        if action.startswith("page.") or action == "browser.open_url":
            return "page"
        if action in {"browser.select_client", "browser.select_tab"}:
            return "session"
        if action.startswith("computer.select_") or action in {
            "computer.show_app",
            "computer.focus_app",
            "computer.activate_app",
        }:
            return "window"
        return "visible_ui"

    def _extract_snapshot(self, roots: list[dict[str, Any]], action: str) -> dict[str, Any] | None:
        snapshot: dict[str, Any] = {}
        session = self._first_mapping(roots, "browser_session", "session")
        windows_list = self._first_sequence(roots, "windows")
        tabs_list = self._first_sequence(roots, "tabs")
        clients_list = self._first_sequence(roots, "clients")
        tab_value = self._first_mapping(roots, "tab")
        client_value = self._first_mapping(roots, "client", "active_client")
        active_client_id = self._first_string(roots, "active_client_id")
        cursor = self._first_point(roots, "cursor")
        ai_cursor = self._first_point(roots, "ai_cursor")
        has_explicit_state = any(
            (
                session is not None,
                windows_list is not None,
                tabs_list is not None,
                clients_list is not None,
                tab_value is not None,
                client_value is not None,
                bool(active_client_id),
                cursor is not None,
                ai_cursor is not None,
                action in _SNAPSHOT_ACTIONS,
            )
        )
        if not has_explicit_state:
            return None

        normalized_session = self._normalize_browser_session(session)
        if normalized_session is not None:
            snapshot["browser_session"] = normalized_session
        active_window = self._first_window(roots, "active_window")
        if active_window is not None:
            snapshot["active_window"] = active_window
        selected_window = self._first_window(roots, "selected_window")
        if selected_window is not None:
            snapshot["selected_window"] = selected_window
        target_window = self._first_window(roots, "target_window")
        if target_window is not None:
            snapshot["target_window"] = target_window
        if cursor is not None:
            snapshot["cursor"] = cursor
        if ai_cursor is not None:
            snapshot["ai_cursor"] = ai_cursor
        windows = self._bounded_windows(windows_list)
        if windows is not None:
            snapshot.update(windows)
        tab = self._normalize_tab(tab_value)
        if tab is not None:
            snapshot["tab"] = tab
        tabs = self._bounded_tabs(tabs_list)
        if tabs is not None:
            snapshot.update(tabs)
        client = self._normalize_client(client_value)
        if client is not None:
            snapshot["client"] = client
        clients = self._bounded_clients(clients_list)
        if clients is not None:
            snapshot.update(clients)
        if active_client_id:
            snapshot["active_client_id"] = active_client_id
        if snapshot:
            return snapshot
        return None

    def _extract_dom_snapshot(
        self,
        roots: list[dict[str, Any]],
        action: str,
    ) -> dict[str, Any] | None:
        candidate: Any = None
        owner: dict[str, Any] | None = None
        for root in roots:
            value = root.get("snapshot")
            if isinstance(value, (dict, list)):
                candidate = value
                owner = root
                break
        if candidate is None and action in _DOM_ACTIONS:
            for root in roots:
                if isinstance(root.get("elements"), list):
                    candidate = {"elements": root.get("elements"), "url": root.get("url"), "title": root.get("title")}
                    owner = root
                    break
        if candidate is None:
            return None
        if not self._looks_like_dom_snapshot(candidate, action):
            return None

        payload: dict[str, Any] = {}
        source = candidate if isinstance(candidate, dict) else {}
        url = self._clean_string(source.get("url") if isinstance(candidate, dict) else None) or self._clean_string(
            owner.get("url") if isinstance(owner, dict) else None
        )
        title = self._clean_string(source.get("title") if isinstance(candidate, dict) else None) or self._clean_string(
            owner.get("title") if isinstance(owner, dict) else None
        )
        if url:
            payload["url"] = url
        if title:
            payload["title"] = title
        tab_id = self._coerce_int(
            source.get("tab_id") if isinstance(candidate, dict) else None
        )
        if tab_id is None and isinstance(owner, dict):
            tab_id = self._coerce_int(owner.get("tab_id"))
        if tab_id is not None:
            payload["tab_id"] = tab_id

        nodes_source: list[Any] = []
        if isinstance(candidate, list):
            nodes_source = list(candidate)
        elif isinstance(candidate, dict):
            if isinstance(candidate.get("nodes"), list):
                nodes_source = list(candidate.get("nodes") or [])
            elif isinstance(candidate.get("elements"), list):
                nodes_source = list(candidate.get("elements") or [])
        normalized_nodes = [node for node in (self._normalize_dom_node(item) for item in nodes_source) if node]
        if normalized_nodes:
            payload["node_count"] = len(normalized_nodes)
            payload["nodes"] = normalized_nodes[: self._limits.max_dom_nodes]
            omitted = len(normalized_nodes) - len(payload["nodes"])
            if omitted > 0:
                payload["nodes_omitted"] = omitted
                payload["truncated"] = True

        if isinstance(candidate, dict):
            for key in ("text", "markdown", "html"):
                value = self._clean_string(candidate.get(key), limit=self._limits.max_string_length)
                if value:
                    payload[key] = value
        return payload or None

    def _extract_screenshots(
        self,
        roots: list[dict[str, Any]],
        action: str,
    ) -> list[dict[str, Any]]:
        ordered_keys: list[str] = []
        merged: dict[str, dict[str, Any]] = {}
        for root in roots:
            for source_name, candidate in self._screenshot_candidates(root):
                normalized = self._normalize_screenshot(candidate, fallback=root, action=action, source=source_name)
                if normalized is None:
                    continue
                key = self._screenshot_key(normalized)
                if key not in merged:
                    ordered_keys.append(key)
                    merged[key] = normalized
                else:
                    merged[key] = self._merge_dicts(merged[key], normalized)
        return [merged[key] for key in ordered_keys[: self._limits.max_screenshots]]

    @staticmethod
    def _screenshot_candidates(root: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        candidates: list[tuple[str, dict[str, Any]]] = []
        visual_feedback = root.get("visual_feedback")
        if isinstance(visual_feedback, dict) and BrowserStateNormalizer._looks_like_screenshot_payload(visual_feedback):
            candidates.append(("visual_feedback", visual_feedback))
        if BrowserStateNormalizer._looks_like_screenshot_payload(root):
            candidates.append(("result", root))
        widget = root.get("widget")
        if isinstance(widget, dict) and BrowserStateNormalizer._looks_like_screenshot_payload(widget):
            candidates.append(("widget", widget))
        capture = root.get("capture")
        if isinstance(capture, dict) and BrowserStateNormalizer._looks_like_screenshot_payload(capture):
            candidates.append(("capture", capture))
        return candidates

    @staticmethod
    def _looks_like_screenshot_payload(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        return any(
            value.get(key)
            for key in ("data_url", "dataUrl", "path", "screenshot_path", "model_image_path", "model_image")
        )

    def _normalize_screenshot(
        self,
        value: dict[str, Any],
        *,
        fallback: dict[str, Any],
        action: str,
        source: str,
    ) -> dict[str, Any] | None:
        screenshot: dict[str, Any] = {"sources": [source]}
        resolved_action = self._clean_string(value.get("action")) or self._clean_string(fallback.get("action")) or action
        if resolved_action:
            screenshot["action"] = resolved_action
        feedback_type = self._clean_string(value.get("type"))
        if feedback_type:
            screenshot["feedback_type"] = feedback_type
        data_url = self._clean_data_url(value.get("data_url") or value.get("dataUrl") or value.get("model_image"))
        if not data_url:
            data_url = self._clean_data_url(fallback.get("data_url") or fallback.get("dataUrl") or fallback.get("model_image"))
        if data_url:
            screenshot["data_url"] = data_url
        path = self._clean_string(value.get("path") or value.get("screenshot_path"))
        if not path:
            path = self._clean_string(fallback.get("path") or fallback.get("screenshot_path"))
        if path:
            screenshot["path"] = path
        model_image_path = self._clean_string(value.get("model_image_path"))
        if not model_image_path:
            model_image_path = self._clean_string(fallback.get("model_image_path"))
        if model_image_path:
            screenshot["model_image_path"] = model_image_path
        mime_type = self._clean_string(value.get("mime_type")) or self._clean_string(fallback.get("mime_type"))
        if mime_type:
            screenshot["mime_type"] = mime_type
        image_size = self._normalize_size(value.get("image_size")) or self._normalize_size(fallback.get("image_size"))
        if image_size is not None:
            screenshot["image_size"] = image_size
        model_image_size = self._normalize_size(value.get("model_image_size")) or self._normalize_size(
            fallback.get("model_image_size")
        )
        if model_image_size is not None:
            screenshot["model_image_size"] = model_image_size
        coordinate_system = self._normalize_coordinate_system(value.get("coordinate_system")) or self._normalize_coordinate_system(
            fallback.get("coordinate_system")
        )
        if coordinate_system is not None:
            screenshot["coordinate_system"] = coordinate_system
        action_coordinate_system = self._normalize_coordinate_system(
            value.get("action_coordinate_system")
        ) or self._normalize_coordinate_system(fallback.get("action_coordinate_system"))
        if action_coordinate_system is not None:
            screenshot["action_coordinate_system"] = action_coordinate_system
        crop_reference = self._normalize_crop_reference(value.get("crop_reference")) or self._normalize_crop_reference(
            fallback.get("crop_reference")
        )
        if crop_reference is not None:
            screenshot["crop_reference"] = crop_reference
        marker = self._normalize_point(value.get("marker")) or self._normalize_point(value.get("click_marker"))
        if marker is None:
            marker = self._normalize_point(fallback.get("marker")) or self._normalize_point(fallback.get("click_marker"))
        if marker is not None:
            screenshot["marker"] = marker
        click_marker = self._normalize_point(value.get("click_marker")) or self._normalize_point(fallback.get("click_marker"))
        if click_marker is not None:
            screenshot["click_marker"] = click_marker
        drag_marker = self._normalize_drag_marker(value.get("drag_marker")) or self._normalize_drag_marker(
            fallback.get("drag_marker")
        )
        if drag_marker is not None:
            screenshot["drag_marker"] = drag_marker
        for window_key in ("target_window", "active_window", "selected_window"):
            normalized_window = self._normalize_window(value.get(window_key)) or self._normalize_window(fallback.get(window_key))
            if normalized_window is not None:
                screenshot[window_key] = normalized_window
        if len(screenshot) == 1:
            return None
        return screenshot

    @staticmethod
    def _screenshot_key(screenshot: dict[str, Any]) -> str:
        for key in ("data_url", "model_image_path", "path"):
            value = screenshot.get(key)
            if isinstance(value, str) and value:
                return f"{key}:{value}"
        return "source:" + ",".join(str(item) for item in screenshot.get("sources") or ["result"])

    def _normalize_window(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        x = self._coerce_int(value.get("x"), default=0)
        y = self._coerce_int(value.get("y"), default=0)
        width = self._coerce_int(value.get("width"))
        height = self._coerce_int(value.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            return None
        normalized: dict[str, Any] = {
            "app": self._clean_string(value.get("app") or value.get("process")),
            "title": self._clean_string(value.get("title") or value.get("name")),
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "active": bool(value.get("active")),
        }
        window_id = self._coerce_int(value.get("window_id") or value.get("id"))
        if window_id is not None:
            normalized["window_id"] = window_id
        pid = self._coerce_int(value.get("pid"))
        if pid is not None:
            normalized["pid"] = pid
        for rect_key in ("capture_rect", "content_rect"):
            rect = self._normalize_rect(value.get(rect_key))
            if rect is not None:
                normalized[rect_key] = rect
        frame_window_ids = value.get("frame_window_ids")
        if isinstance(frame_window_ids, list):
            ids = [item for item in (self._coerce_int(raw) for raw in frame_window_ids) if item is not None]
            if ids:
                normalized["frame_window_ids"] = ids
        capture_method = self._clean_string(value.get("capture_method"))
        if capture_method:
            normalized["capture_method"] = capture_method
        return normalized

    def _normalize_rect(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        x = self._coerce_int(value.get("x"), default=0)
        y = self._coerce_int(value.get("y"), default=0)
        width = self._coerce_int(value.get("width"))
        height = self._coerce_int(value.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            return None
        return {"x": x, "y": y, "width": width, "height": height}

    def _normalize_point(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, Any] = {}
        x = self._coerce_int(value.get("x"))
        y = self._coerce_int(value.get("y"))
        if x is not None:
            normalized["x"] = x
        if y is not None:
            normalized["y"] = y
        screen_x = self._coerce_int(value.get("screen_x"))
        screen_y = self._coerce_int(value.get("screen_y"))
        if screen_x is not None:
            normalized["screen_x"] = screen_x
        if screen_y is not None:
            normalized["screen_y"] = screen_y
        coordinate_space = self._clean_string(value.get("coordinate_space"))
        if coordinate_space:
            normalized["coordinate_space"] = coordinate_space
        origin = self._clean_string(value.get("origin"))
        if origin:
            normalized["origin"] = origin
        return normalized or None

    def _normalize_drag_marker(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        start = self._normalize_point(value.get("from"))
        end = self._normalize_point(value.get("to"))
        if start is None and end is None:
            return None
        normalized: dict[str, Any] = {}
        if start is not None:
            normalized["from"] = start
        if end is not None:
            normalized["to"] = end
        return normalized

    def _normalize_coordinate_system(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, Any] = {}
        for key in ("origin", "unit", "screen", "space", "coordinate_space"):
            text = self._clean_string(value.get(key))
            if text:
                normalized[key] = text
        for key in ("x", "y", "width", "height"):
            coerced = self._coerce_int(value.get(key))
            if coerced is not None:
                normalized[key] = coerced
        for key in ("x_range", "y_range"):
            raw_range = value.get(key)
            if isinstance(raw_range, (list, tuple)) and len(raw_range) >= 2:
                start = self._coerce_int(raw_range[0])
                end = self._coerce_int(raw_range[1])
                if start is not None and end is not None:
                    normalized[key] = [start, end]
        return normalized or None

    def _normalize_crop_reference(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, Any] = {}
        for key in ("source", "source_path", "source_role", "coordinate_space"):
            text = self._clean_string(value.get(key))
            if text:
                normalized[key] = text
        if "source_is_crop" in value:
            normalized["source_is_crop"] = bool(value.get("source_is_crop"))
        box = self._normalize_rect(value.get("box"))
        if box is not None:
            normalized["box"] = box
        action_box = self._normalize_coordinate_system(value.get("action_box"))
        if action_box is not None:
            normalized["action_box"] = action_box
        source_image_size = self._normalize_size(value.get("source_image_size"))
        if source_image_size is not None:
            normalized["source_image_size"] = source_image_size
        source_action = self._normalize_coordinate_system(value.get("source_action_coordinate_system"))
        if source_action is not None:
            normalized["source_action_coordinate_system"] = source_action
        return normalized or None

    def _normalize_size(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        width = self._coerce_int(value.get("width"))
        height = self._coerce_int(value.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            return None
        return {"width": width, "height": height}

    def _normalize_tab(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, Any] = {}
        tab_id = self._coerce_int(value.get("id") or value.get("tab_id"))
        if tab_id is not None:
            normalized["id"] = tab_id
        window_id = self._coerce_int(value.get("window_id"))
        if window_id is not None:
            normalized["window_id"] = window_id
        active = value.get("active")
        if isinstance(active, bool):
            normalized["active"] = active
        for key in ("title", "url", "status"):
            text = self._clean_string(value.get(key))
            if text:
                normalized[key] = text
        return normalized or None

    def _normalize_client(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, Any] = {}
        for key in ("client_id", "browser_name", "label"):
            text = self._clean_string(value.get(key))
            if text:
                normalized[key] = text
        for key in ("active_tab_id",):
            coerced = self._coerce_int(value.get(key))
            if coerced is not None:
                normalized[key] = coerced
        for key in ("is_active", "stale"):
            if key in value:
                normalized[key] = bool(value.get(key))
        return normalized or None

    def _normalize_browser_session(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, Any] = {}
        for key in ("last_url", "active_profile_id", "updated_at"):
            text = self._clean_string(value.get(key))
            if text:
                normalized[key] = text
        if "last_opened_with_managed_profile" in value:
            normalized["last_opened_with_managed_profile"] = bool(value.get("last_opened_with_managed_profile"))
        return normalized or None

    def _bounded_windows(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, list):
            return None
        normalized = [item for item in (self._normalize_window(entry) for entry in value) if item]
        if not normalized:
            return None
        visible = normalized[: self._limits.max_windows]
        payload: dict[str, Any] = {"windows": visible}
        omitted = len(normalized) - len(visible)
        if omitted > 0:
            payload["windows_omitted"] = omitted
        return payload

    def _bounded_tabs(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, list):
            return None
        normalized = [item for item in (self._normalize_tab(entry) for entry in value) if item]
        if not normalized:
            return None
        visible = normalized[: self._limits.max_tabs]
        payload: dict[str, Any] = {"tabs": visible}
        omitted = len(normalized) - len(visible)
        if omitted > 0:
            payload["tabs_omitted"] = omitted
        return payload

    def _bounded_clients(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, list):
            return None
        normalized = [item for item in (self._normalize_client(entry) for entry in value) if item]
        if not normalized:
            return None
        visible = normalized[: self._limits.max_clients]
        payload: dict[str, Any] = {"clients": visible}
        omitted = len(normalized) - len(visible)
        if omitted > 0:
            payload["clients_omitted"] = omitted
        return payload

    def _normalize_dom_node(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, Any] = {}
        string_keys = (
            "element_id",
            "tag",
            "tag_name",
            "role",
            "text",
            "selector",
            "name",
            "type",
            "value",
            "label",
            "placeholder",
            "title",
            "href",
        )
        for key in string_keys:
            limit = self._limits.max_dom_text_length if key in {"text", "value", "label", "title"} else self._limits.max_string_length
            text = self._clean_string(value.get(key), limit=limit)
            if text:
                normalized[key] = text
        for key in ("x", "y", "width", "height", "tab_index"):
            coerced = self._coerce_int(value.get(key))
            if coerced is not None:
                normalized[key] = coerced
        for key in ("checked", "disabled", "focused", "visible"):
            if key in value:
                normalized[key] = bool(value.get(key))
        attributes = value.get("attributes")
        if isinstance(attributes, dict):
            normalized_attributes: dict[str, str] = {}
            for raw_key in list(attributes.keys())[: self._limits.max_dom_attributes]:
                key = self._clean_string(raw_key)
                val = self._clean_string(attributes.get(raw_key), limit=self._limits.max_dom_text_length)
                if key and val:
                    normalized_attributes[key] = val
            if normalized_attributes:
                normalized["attributes"] = normalized_attributes
        return normalized or None

    @staticmethod
    def _looks_like_dom_snapshot(candidate: Any, action: str) -> bool:
        if action in _DOM_ACTIONS:
            return True
        if isinstance(candidate, list):
            return True
        if not isinstance(candidate, dict):
            return False
        return any(key in candidate for key in ("nodes", "elements", "html", "markdown", "text", "url", "title"))

    def _merge_dicts(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        merged = dict(left)
        for key, value in right.items():
            if key == "sources":
                existing = list(merged.get("sources") or [])
                for item in value if isinstance(value, list) else [value]:
                    if item not in existing:
                        existing.append(item)
                merged["sources"] = existing
                continue
            if key not in merged or merged[key] in (None, "", [], {}):
                merged[key] = value
                continue
            if isinstance(merged[key], dict) and isinstance(value, dict):
                nested = dict(merged[key])
                for nested_key, nested_value in value.items():
                    if nested_key not in nested or nested[nested_key] in (None, "", [], {}):
                        nested[nested_key] = nested_value
                merged[key] = nested
        return merged

    def _first_mapping(self, roots: list[dict[str, Any]], *keys: str) -> dict[str, Any] | None:
        for root in roots:
            for key in keys:
                value = root.get(key)
                if isinstance(value, dict):
                    return value
        return None

    def _first_sequence(self, roots: list[dict[str, Any]], *keys: str) -> list[Any] | None:
        for root in roots:
            for key in keys:
                value = root.get(key)
                if isinstance(value, list):
                    return value
        return None

    def _first_string(self, roots: list[dict[str, Any]], *keys: str) -> str:
        for root in roots:
            for key in keys:
                value = self._clean_string(root.get(key))
                if value:
                    return value
        return ""

    def _first_nested_string(self, roots: list[dict[str, Any]], key: str, nested_key: str) -> str:
        for root in roots:
            value = root.get(key)
            if isinstance(value, dict):
                text = self._clean_string(value.get(nested_key))
                if text:
                    return text
        return ""

    def _first_int(self, roots: list[dict[str, Any]], *keys: str) -> int | None:
        for root in roots:
            for key in keys:
                value = self._coerce_int(root.get(key))
                if value is not None:
                    return value
        return None

    def _first_window(self, roots: list[dict[str, Any]], *keys: str) -> dict[str, Any] | None:
        for root in roots:
            for key in keys:
                window = self._normalize_window(root.get(key))
                if window is not None:
                    return window
        return None

    def _first_point(self, roots: list[dict[str, Any]], *keys: str) -> dict[str, Any] | None:
        for root in roots:
            for key in keys:
                point = self._normalize_point(root.get(key))
                if point is not None:
                    return point
        return None

    def _clean_string(self, value: Any, *, limit: int | None = None) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        max_length = self._limits.max_string_length if limit is None else limit
        if max_length <= 0:
            return ""
        if len(text) <= max_length:
            return text
        if max_length <= 3:
            return text[:max_length]
        return text[: max_length - 3].rstrip() + "..."

    def _clean_data_url(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text or not text.startswith("data:image/"):
            return ""
        return text

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _coerce_int(value: Any, default: int | None = None) -> int | None:
        if value is None or value == "":
            return default
        try:
            return int(float(value))
        except Exception:
            return default


def emit_browser_state_events(
    tool_name: str,
    result: Any,
    *,
    tool_call_id: str | None = None,
    action: str | None = None,
    timestamp: Any = None,
    state_revision: int = 0,
    limits: BrowserStateLimits | None = None,
) -> BrowserStateEmission:
    normalizer = BrowserStateNormalizer(state_revision=state_revision, limits=limits)
    return normalizer.emit_from_tool_result(
        tool_name,
        result,
        tool_call_id=tool_call_id,
        action=action,
        timestamp=timestamp,
    )


__all__ = [
    "BrowserStateEmission",
    "BrowserStateLimits",
    "BrowserStateNormalizer",
    "emit_browser_state_events",
]
