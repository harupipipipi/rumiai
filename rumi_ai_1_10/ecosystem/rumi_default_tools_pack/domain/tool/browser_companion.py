from __future__ import annotations

import base64
import binascii
import re
import time
from pathlib import Path
from typing import Any

from .browser_companion_bridge import (
    BrowserCompanionBridgeStore,
    candidate_base_urls,
)


_DATA_URL_RE = re.compile(r"^data:(?P<mime>image/[a-z0-9.+-]+);base64,(?P<data>.+)$", re.IGNORECASE)


class BrowserCompanionController:
    """Cookie-bearing browser extension bridge for DOM-aware browser control."""

    def __init__(
        self,
        *,
        artifact_root: Path | None = None,
        bridge_store: BrowserCompanionBridgeStore | None = None,
    ) -> None:
        pack_root = Path(__file__).resolve().parents[2]
        self._artifact_root = artifact_root or pack_root / "user_data" / "artifacts" / "browser_companion"
        self._bridge = bridge_store or BrowserCompanionBridgeStore()

    def run(self, action: str, payload: dict[str, Any] | None = None, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        context = context if isinstance(context, dict) else {}
        normalized = self._normalize_action(action)
        if normalized in {"session", "bridge.status"}:
            return self._session(context)
        if normalized == "bridge.pairing":
            return self._pairing(context, rotate=bool(payload.get("rotate")))
        if normalized in {"browser.clients", "browser.sessions"}:
            return self._clients()
        if normalized == "browser.select_client":
            return self._select_client(payload)
        if normalized == "browser.tabs":
            return self._run_remote("browser.tabs", payload, context, timeout_seconds=10.0)
        if normalized == "browser.select_tab":
            return self._run_remote("browser.select_tab", payload, context, timeout_seconds=10.0)
        if normalized == "page.navigate":
            return self._run_remote("page.navigate", payload, context, timeout_seconds=20.0)
        if normalized == "page.snapshot":
            return self._run_remote("page.snapshot", payload, context, timeout_seconds=20.0, attach_capture=bool(payload.get("include_capture")))
        if normalized == "page.capture":
            return self._run_remote("page.capture", payload, context, timeout_seconds=20.0, attach_capture=True)
        if normalized == "page.extract":
            return self._run_remote("page.extract", payload, context, timeout_seconds=20.0)
        if normalized == "page.click":
            return self._run_remote("page.click", payload, context, timeout_seconds=20.0)
        if normalized == "page.type":
            return self._run_remote("page.type", payload, context, timeout_seconds=20.0)
        if normalized == "page.press":
            return self._run_remote("page.press", payload, context, timeout_seconds=20.0)
        if normalized == "page.scroll":
            return self._run_remote("page.scroll", payload, context, timeout_seconds=20.0)
        if normalized == "page.highlight":
            return self._run_remote("page.highlight", payload, context, timeout_seconds=20.0)
        if normalized == "page.clear_highlight":
            return self._run_remote("page.clear_highlight", payload, context, timeout_seconds=20.0)
        raise ValueError(f"Unsupported browser companion action: {action}")

    @staticmethod
    def _normalize_action(action: str) -> str:
        raw = str(action or "").strip()
        aliases = {
            "": "session",
            "pairing": "bridge.pairing",
            "clients": "browser.clients",
            "select_client": "browser.select_client",
            "tabs": "browser.tabs",
            "select_tab": "browser.select_tab",
            "navigate": "page.navigate",
            "snapshot": "page.snapshot",
            "capture": "page.capture",
            "extract": "page.extract",
            "click": "page.click",
            "type": "page.type",
            "press": "page.press",
            "scroll": "page.scroll",
            "highlight": "page.highlight",
            "clear_highlight": "page.clear_highlight",
        }
        return aliases.get(raw, raw)

    def _pairing(self, context: dict[str, Any], *, rotate: bool) -> dict[str, Any]:
        config = self._bridge.ensure_pairing(rotate=rotate)
        return {
            "action": "bridge.pairing",
            "pairing": {
                "pairing_token": config.get("pairing_token"),
                "server_urls": candidate_base_urls(context),
                "config_dir": str(self._bridge.root_dir),
                "updated_at": config.get("updated_at") or config.get("created_at"),
            },
        }

    def _session(self, context: dict[str, Any]) -> dict[str, Any]:
        clients = self._bridge.list_clients()
        active_client = None
        for client in clients:
            if client.get("is_active"):
                active_client = client
                break
        return {
            "action": "session",
            "pairing": self._pairing(context, rotate=False).get("pairing"),
            "clients": clients,
            "active_client_id": active_client.get("client_id") if isinstance(active_client, dict) else self._bridge.active_client_id(),
            "active_client": active_client,
            "capabilities": {
                "multi_browser": True,
                "dom_snapshot": True,
                "semantic_dom": True,
                "accessible_labels": True,
                "user_session_cookies": True,
                "browser_tab_capture": True,
                "element_actions": ["click", "type", "press", "scroll", "extract", "highlight", "clear_highlight"],
            },
        }

    def _clients(self) -> dict[str, Any]:
        return {
            "action": "browser.clients",
            "clients": self._bridge.list_clients(),
            "active_client_id": self._bridge.active_client_id(),
        }

    def _select_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._bridge.resolve_client(
            client_id=str(payload.get("client_id") or ""),
            browser=str(payload.get("browser") or payload.get("browser_name") or ""),
            label=str(payload.get("label") or ""),
        )
        if client is None:
            return {
                "action": "browser.select_client",
                "is_error": True,
                "reason": "No connected browser companion client matched the request.",
                "clients": self._bridge.list_clients(include_stale=True),
            }
        self._bridge.set_active_client(str(client.get("client_id") or ""))
        client = self._bridge.get_client(str(client.get("client_id") or "")) or client
        return {
            "action": "browser.select_client",
            "client": client,
            "active_client_id": client.get("client_id"),
        }

    def _resolve_target_client(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        explicit = self._bridge.resolve_client(
            client_id=str(payload.get("client_id") or ""),
            browser=str(payload.get("browser") or payload.get("browser_name") or ""),
            label=str(payload.get("label") or ""),
        )
        if explicit is not None:
            return explicit
        active_client_id = self._bridge.active_client_id()
        if active_client_id:
            active = self._bridge.get_client(active_client_id)
            if active is not None:
                return active
        clients = self._bridge.list_clients()
        return clients[0] if clients else None

    def _run_remote(
        self,
        remote_action: str,
        payload: dict[str, Any],
        context: dict[str, Any],
        *,
        timeout_seconds: float,
        attach_capture: bool = False,
    ) -> dict[str, Any]:
        client = self._resolve_target_client(payload)
        if client is None:
            return {
                "action": remote_action,
                "is_error": True,
                "reason": "No connected browser companion clients are available. Pair the extension first.",
                "pairing": self._pairing(context, rotate=False).get("pairing"),
                "clients": self._bridge.list_clients(include_stale=True),
            }
        self._bridge.set_active_client(str(client.get("client_id") or ""))
        remote_payload = self._remote_payload(payload)
        if self._include_values_allowed(remote_action, payload, context):
            remote_payload["include_values"] = True
            remote_payload["include_values_approved"] = True
        if remote_action in {"page.click", "page.press"} and self._context_allows_value_inclusion(context):
            remote_payload["approval_evidence"] = "tool_server_approval"
        if remote_action.startswith("page.") and remote_payload.get("tab_id") is None:
            active_tab_id = client.get("active_tab_id")
            if active_tab_id is not None:
                remote_payload["tab_id"] = active_tab_id
        command = self._bridge.create_command(
            str(client.get("client_id") or ""),
            {
                "action": remote_action,
                "payload": remote_payload,
            },
        )
        completed = self._bridge.wait_for_command(
            str(command.get("command_id") or ""),
            timeout_seconds=timeout_seconds,
        )
        if completed.get("status") != "completed":
            return {
                "action": remote_action,
                "is_error": True,
                "reason": "Timed out waiting for the browser companion extension to respond.",
                "client": client,
                "command_id": command.get("command_id"),
            }
        result = completed.get("result") if isinstance(completed.get("result"), dict) else {}
        semantics = self._action_semantics(remote_action, result)
        output = {
            "action": remote_action,
            "client": client,
            "client_id": client.get("client_id"),
            "command_id": command.get("command_id"),
            **semantics,
            "result": result,
        }
        if bool(result.get("is_error")):
            output["is_error"] = True
            output["reason"] = result.get("reason") or result.get("error") or "Browser companion command failed."
        else:
            output["is_error"] = False
        if attach_capture or self._remote_result_contains_capture(result):
            artifact = self._save_capture_artifact(result, remote_action)
            if artifact is not None:
                output.update(artifact)
        if isinstance(result.get("snapshot"), dict):
            output["snapshot"] = result.get("snapshot")
        elif isinstance(result.get("snapshot"), list):
            output["snapshot"] = result.get("snapshot")
        if "tabs" in result:
            output["tabs"] = result.get("tabs")
        if "tab" in result:
            output["tab"] = result.get("tab")
        if "url" in result and not output.get("url"):
            output["url"] = result.get("url")
        if "data" in result and "data" not in output:
            output["data"] = result.get("data")
        if "elements" in result:
            output["elements"] = result.get("elements")
        return output

    @staticmethod
    def _action_semantics(remote_action: str, result: dict[str, Any]) -> dict[str, bool]:
        requires_foreground = result.get("requires_foreground")
        can_parallel = result.get("can_parallel_user_work")
        if isinstance(requires_foreground, bool) and isinstance(can_parallel, bool):
            return {
                "requires_foreground": requires_foreground,
                "can_parallel_user_work": can_parallel,
            }
        capture = result.get("capture") if isinstance(result.get("capture"), dict) else {}
        if remote_action == "page.capture" or isinstance(capture.get("data_url"), str):
            return {
                "requires_foreground": True,
                "can_parallel_user_work": False,
            }
        if remote_action == "browser.select_tab":
            return {
                "requires_foreground": True,
                "can_parallel_user_work": False,
            }
        if remote_action in {
            "page.navigate",
            "page.click",
            "page.type",
            "page.press",
            "page.scroll",
            "page.highlight",
        }:
            return {
                "requires_foreground": True,
                "can_parallel_user_work": False,
            }
        if remote_action in {
            "browser.tabs",
            "page.snapshot",
            "page.extract",
            "page.clear_highlight",
        }:
            return {
                "requires_foreground": False,
                "can_parallel_user_work": True,
            }
        return {}

    @staticmethod
    def _remote_payload(payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "client_id",
            "browser",
            "browser_name",
            "label",
            "tab_id",
            "window_id",
            "url",
            "element_id",
            "selector",
            "selectors",
            "text",
            "key",
            "keys",
            "code",
            "modifiers",
            "repeat",
            "direction",
            "amount",
            "x",
            "y",
            "top",
            "left",
            "delta_x",
            "delta_y",
            "behavior",
            "mode",
            "limit",
            "include_hidden",
            "include_html",
            "include_capture",
            "include_attributes",
            "attribute_names",
            "wait_for",
            "timeout_ms",
            "format",
            "quality",
            "duration_ms",
            "color",
            "label",
            "clear_existing",
            "include_semantics",
        }
        return {key: value for key, value in payload.items() if key in allowed and value is not None}

    @classmethod
    def _include_values_allowed(cls, remote_action: str, payload: dict[str, Any], context: dict[str, Any]) -> bool:
        if remote_action not in {"page.snapshot", "page.extract"}:
            return False
        if not cls._truthy(payload.get("include_values")):
            return False
        return cls._context_allows_value_inclusion(context)

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on", "allow", "allowed"}
        return False

    @classmethod
    def _context_allows_value_inclusion(cls, context: dict[str, Any]) -> bool:
        if not isinstance(context, dict):
            return False
        if context.get("_tool_server_approval_token_valid") is True or context.get("_tool_server_approved") is True:
            return True
        policy = context.get("profile_policy")
        if isinstance(policy, dict) and cls._truthy(policy.get("yolo_mode")):
            return True
        return cls._truthy(context.get("yolo_mode"))

    @staticmethod
    def _remote_result_contains_capture(result: dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            return False
        if isinstance(result.get("data_url"), str) and result.get("data_url"):
            return True
        capture = result.get("capture")
        return isinstance(capture, dict) and isinstance(capture.get("data_url"), str) and bool(capture.get("data_url"))

    def _save_capture_artifact(self, result: dict[str, Any], remote_action: str) -> dict[str, Any] | None:
        capture = result.get("capture") if isinstance(result.get("capture"), dict) else result
        data_url = str(capture.get("data_url") or "").strip()
        match = _DATA_URL_RE.match(data_url)
        if not match:
            return None
        try:
            raw = base64.b64decode(match.group("data"), validate=True)
        except (ValueError, binascii.Error):
            return None
        extension = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
        }.get(match.group("mime").lower(), "png")
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        path = self._artifact_root / f"{remote_action.replace('.', '-')}-{int(time.time() * 1000)}.{extension}"
        path.write_bytes(raw)
        record = {
            "path": str(path),
            "mime_type": match.group("mime"),
            "data_url": data_url,
        }
        if isinstance(capture.get("image_size"), dict):
            record["image_size"] = capture.get("image_size")
        if "target_window" in capture:
            record["target_window"] = capture.get("target_window")
        if "marker" in capture:
            record["marker"] = capture.get("marker")
        if "click_marker" in capture:
            record["click_marker"] = capture.get("click_marker")
        if "drag_marker" in capture:
            record["drag_marker"] = capture.get("drag_marker")
        return record
