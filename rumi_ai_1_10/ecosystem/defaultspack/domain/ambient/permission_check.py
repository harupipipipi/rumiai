from __future__ import annotations

from typing import Any


MICROPHONE_CAPTURE = "host.microphone.capture"
CAMERA_CAPTURE = "host.camera.capture"
AMBIENT_TRIGGER_DISPATCH = "ambient.trigger.dispatch"

REQUIRED_PERMISSIONS = (MICROPHONE_CAPTURE, CAMERA_CAPTURE, AMBIENT_TRIGGER_DISPATCH)
LEGACY_PERMISSION_ALIASES = {
    "microphone.capture": MICROPHONE_CAPTURE,
    "camera.capture": CAMERA_CAPTURE,
}


def normalize_ambient_permission_id(permission_id: str) -> str:
    raw = str(permission_id or "").strip()
    return LEGACY_PERMISSION_ALIASES.get(raw, raw)


def permissions_for_source(source: str) -> tuple[str, ...]:
    if source == "microphone":
        return (MICROPHONE_CAPTURE, AMBIENT_TRIGGER_DISPATCH)
    if source == "camera":
        return (CAMERA_CAPTURE, AMBIENT_TRIGGER_DISPATCH)
    return (AMBIENT_TRIGGER_DISPATCH,)


def missing_rumi_permissions(
    state: dict[str, Any],
    source: str,
    *,
    needs_microphone: bool = False,
) -> list[str]:
    permissions = state.get("permissions") if isinstance(state.get("permissions"), dict) else {}
    rumi = permissions.get("rumi") if isinstance(permissions.get("rumi"), dict) else {}
    missing: list[str] = []
    required = list(permissions_for_source(source))
    if needs_microphone and MICROPHONE_CAPTURE not in required:
        required.insert(0, MICROPHONE_CAPTURE)
    for permission_id in required:
        entry = rumi.get(permission_id) if isinstance(rumi.get(permission_id), dict) else {}
        if not bool(entry.get("granted")):
            missing.append(permission_id)
    return missing
