from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from .permission_check import (
    AMBIENT_TRIGGER_DISPATCH,
    CAMERA_CAPTURE,
    MICROPHONE_CAPTURE,
    LEGACY_PERMISSION_ALIASES,
    normalize_ambient_permission_id,
)


class AmbientStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _state_path()

    def read(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                data = parsed
        except FileNotFoundError:
            data = {}
        except (json.JSONDecodeError, OSError):
            data = {}
        base = _default_state()
        _deep_update(base, data)
        _migrate_legacy_permissions(base)
        _migrate_legacy_gesture_thresholds(base)
        _migrate_legacy_hooks(base)
        return base

    def write(self, state: dict[str, Any]) -> dict[str, Any]:
        clean = _privacy_safe_state(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return clean

    def start_monitor(self, *, voice_wake: bool = True, gesture_pinch: bool = True) -> dict[str, Any]:
        state = self.read()
        state["ambient_monitor"]["enabled"] = True
        state["ambient_monitor"]["updated_at"] = _now()
        if voice_wake:
            state["services"]["voice_wake_monitor"]["enabled"] = True
            state["services"]["voice_wake_monitor"]["status"] = "listening"
        if gesture_pinch:
            state["services"]["gesture_wake_monitor"]["enabled"] = True
            state["services"]["gesture_wake_monitor"]["status"] = "listening"
        return self.write(state)

    def stop_monitor(self) -> dict[str, Any]:
        state = self.read()
        state["ambient_monitor"]["enabled"] = False
        state["ambient_monitor"]["updated_at"] = _now()
        for service in ("voice_wake_monitor", "gesture_wake_monitor"):
            state["services"][service]["status"] = "paused"
        return self.write(state)

    def grant_permission(self, permission_id: str, *, os_status: str | None = None) -> dict[str, Any]:
        state = self.read()
        permission_id = normalize_ambient_permission_id(permission_id)
        permission = _rumi_permission(state, permission_id)
        permission["granted"] = True
        permission["updated_at"] = _now()
        if os_status:
            self._update_os_permission_in_state(state, permission_id, os_status)
        return self.write(state)

    def revoke_permission(self, permission_id: str) -> dict[str, Any]:
        state = self.read()
        permission_id = normalize_ambient_permission_id(permission_id)
        permission = _rumi_permission(state, permission_id)
        permission["granted"] = False
        permission["updated_at"] = _now()
        return self.write(state)

    def update_os_permission(self, permission_id: str, status: str) -> dict[str, Any]:
        state = self.read()
        self._update_os_permission_in_state(state, normalize_ambient_permission_id(permission_id), status)
        return self.write(state)

    def update_os_permissions(self, statuses: dict[str, Any]) -> dict[str, Any]:
        state = self.read()
        for permission_id, status in statuses.items():
            if str(permission_id).strip():
                self._update_os_permission_in_state(
                    state,
                    normalize_ambient_permission_id(str(permission_id)),
                    str(status or "unknown"),
                )
        return self.write(state)

    def save_voice_enrollment(self, embedding: list[float], *, threshold: float = 0.88) -> dict[str, Any]:
        state = self.read()
        state["voice_enrollment"] = {
            "enrolled": True,
            "created_at": _now(),
            "classifier": "local_audio_embedding_cosine_v1",
            "embedding": [float(item) for item in embedding],
            "threshold": float(threshold),
        }
        state["services"]["voice_wake_monitor"]["enrolled"] = True
        state["services"]["voice_wake_monitor"]["classifier"] = "local_audio_embedding_cosine_v1"
        return self.write(state)

    def clear_voice_enrollment(self) -> dict[str, Any]:
        state = self.read()
        state["voice_enrollment"] = None
        state["services"]["voice_wake_monitor"]["enrolled"] = False
        return self.write(state)

    def update_routing(self, routing: dict[str, Any]) -> dict[str, Any]:
        state = self.read()
        state["routing"] = _normalized_routing({
            **dict(state.get("routing") if isinstance(state.get("routing"), dict) else {}),
            **dict(routing if isinstance(routing, dict) else {}),
        })
        return self.write(state)

    def mark_trigger(self, event: dict[str, Any]) -> dict[str, Any]:
        state = self.read()
        state["last_trigger"] = {
            "event_id": event.get("event_id"),
            "source": event.get("source"),
            "trigger": event.get("trigger"),
            "status": event.get("status"),
            "created_at": _now(),
        }
        state["services"].setdefault("gesture_wake_monitor", {}).setdefault("last_trigger_at", None)
        if event.get("source") == "camera" and event.get("trigger") == "pinch":
            state["services"]["gesture_wake_monitor"]["last_trigger_at"] = time.time()
        return self.write(state)

    def _update_os_permission_in_state(self, state: dict[str, Any], permission_id: str, status: str) -> None:
        permissions = state.setdefault("permissions", {}).setdefault("os", {})
        permissions.setdefault(permission_id, {})
        permissions[permission_id].update({"status": str(status), "checked_at": _now()})


def _default_state() -> dict[str, Any]:
    return {
        "ambient_monitor": {
            "enabled": False,
            "updated_at": None,
            "controls": ["microphone", "camera"],
        },
        "services": {
            "voice_wake_monitor": {
                "enabled": True,
                "status": "paused",
                "enrolled": False,
                "classifier": "local_audio_embedding_cosine_v1",
                "auto_enroll_first_sample": True,
                "threshold": 0.88,
                "action": "open_input",
            },
            "gesture_wake_monitor": {
                "enabled": True,
                "status": "paused",
                "detector": "thumb_tip_index_tip_distance_v1",
                "pinch_threshold": 0.28,
                "release_threshold": 0.46,
                "cooldown_ms": 1500,
                "last_trigger_at": None,
                "action": "open_input",
            },
        },
        "permissions": {
            "rumi": {
                MICROPHONE_CAPTURE: _permission(MICROPHONE_CAPTURE, "Microphone capture", "high"),
                CAMERA_CAPTURE: _permission(CAMERA_CAPTURE, "Camera capture", "high"),
                AMBIENT_TRIGGER_DISPATCH: _permission(AMBIENT_TRIGGER_DISPATCH, "Ambient trigger dispatch", "medium"),
            },
            "os": {
                MICROPHONE_CAPTURE: {"status": "unknown", "checked_at": None},
                CAMERA_CAPTURE: {"status": "unknown", "checked_at": None},
            },
        },
        "hooks": {
            "defaultspack_input": {"enabled": True, "profile": "defaults.console.input"},
        },
        "privacy": {
            "store_audio": False,
            "store_images": False,
            "audit_event_only": True,
            "audit_fields": ["event_id", "source", "trigger", "status", "action_id", "created_at"],
        },
        "routing": {
            "mode": "selected_chat",
            "conversation_id": None,
            "group_enabled": True,
            "group_id": "gesture",
            "group_title": "Gesture",
            "model": "",
        },
        "voice_enrollment": None,
        "last_trigger": None,
    }


def _permission(permission_id: str, label: str, risk: str) -> dict[str, Any]:
    return {
        "permission_id": permission_id,
        "label": label,
        "risk": risk,
        "granted": False,
        "requires_user_grant": True,
        "updated_at": None,
    }


def _rumi_permission(state: dict[str, Any], permission_id: str) -> dict[str, Any]:
    permission_id = normalize_ambient_permission_id(permission_id)
    permissions = state.setdefault("permissions", {}).setdefault("rumi", {})
    permissions.setdefault(permission_id, _permission(permission_id, permission_id, "medium"))
    return permissions[permission_id]


def _privacy_safe_state(state: dict[str, Any]) -> dict[str, Any]:
    clean = deepcopy(state)
    clean["routing"] = _normalized_routing(clean.get("routing") if isinstance(clean.get("routing"), dict) else {})
    _migrate_legacy_hooks(clean)
    enrollment = clean.get("voice_enrollment")
    if isinstance(enrollment, dict):
        enrollment.pop("raw_audio", None)
        enrollment.pop("samples", None)
        enrollment.pop("audio_embedding_raw", None)
    return clean


def _normalized_routing(value: dict[str, Any]) -> dict[str, Any]:
    mode = str(value.get("mode") or "selected_chat").strip()
    if mode not in {"selected_chat", "startup_new_chat", "always_new_chat"}:
        mode = "selected_chat"
    conversation_id = _clean_optional_string(value.get("conversation_id"))
    group_enabled = _coerce_bool(value.get("group_enabled"), True)
    group_id = _clean_optional_string(value.get("group_id")) or "gesture"
    group_title = _clean_optional_string(value.get("group_title")) or "Gesture"
    model = _clean_optional_string(value.get("model")) or ""
    return {
        "mode": mode,
        "conversation_id": conversation_id,
        "group_enabled": group_enabled,
        "group_id": group_id,
        "group_title": group_title,
        "model": model,
    }


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _state_path() -> Path:
    configured = os.environ.get("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "ambient" / "state.json"


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _migrate_legacy_permissions(state: dict[str, Any]) -> None:
    permissions = state.setdefault("permissions", {})
    for scope in ("rumi", "os"):
        bucket = permissions.get(scope)
        if not isinstance(bucket, dict):
            continue
        for legacy_id, host_id in LEGACY_PERMISSION_ALIASES.items():
            legacy = bucket.pop(legacy_id, None)
            if not isinstance(legacy, dict):
                continue
            current = bucket.get(host_id) if isinstance(bucket.get(host_id), dict) else {}
            merged = dict(current)
            merged.update(legacy)
            if merged.get("permission_id") == legacy_id:
                merged["permission_id"] = host_id
            bucket[host_id] = merged


def _migrate_legacy_gesture_thresholds(state: dict[str, Any]) -> None:
    service = (
        state.get("services", {}).get("gesture_wake_monitor")
        if isinstance(state.get("services"), dict)
        else None
    )
    if not isinstance(service, dict):
        return
    try:
        release_threshold = float(service.get("release_threshold"))
    except (TypeError, ValueError):
        release_threshold = 0.0
    if release_threshold <= 0.38:
        service["release_threshold"] = 0.46


def _migrate_legacy_hooks(state: dict[str, Any]) -> None:
    hooks = state.get("hooks") if isinstance(state.get("hooks"), dict) else {}
    default_input = hooks.get("defaultspack_input") if isinstance(hooks, dict) else {}
    if not isinstance(default_input, dict):
        default_input = {}
    state["hooks"] = {
        "defaultspack_input": {
            "enabled": _coerce_bool(default_input.get("enabled"), True),
            "profile": "defaults.console.input",
        }
    }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
