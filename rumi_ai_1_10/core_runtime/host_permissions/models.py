"""Typed host permission registry models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


HOST_PERMISSION_IDS = frozenset(
    {
        "host.permission.status",
        "host.permission.open_settings",
        "host.intent.execute",
        "host.stream.start",
        "host.stream.stop",
        "host.screen.capture",
        "host.accessibility.read",
        "host.accessibility.mutate",
        "host.input.pointer",
        "host.input.keyboard",
        "host.clipboard.read",
        "host.clipboard.write",
        "host.microphone.capture",
        "host.audio.capture",
        "host.audio.output",
        "host.speech.transcribe",
        "host.speech.synthesize",
        "host.camera.capture",
        "host.file.open_dialog",
        "host.file.read_user_selected",
        "host.file.write_user_selected",
        "host.process.open_url",
        "host.process.launch_app",
        "host.process.exec_guarded",
    }
)


LEGACY_HOST_PERMISSION_ALIASES = {
    "microphone.capture": "host.microphone.capture",
    "camera.capture": "host.camera.capture",
    "host.execute": "host.intent.execute",
}


@dataclass(frozen=True)
class HostPermissionDefinition:
    permission_id: str
    label: str
    risk_level: str = "medium"
    approval_required: bool = True
    stream_allowed: bool = False
    typed_confirmation_required: bool = False
    max_duration_ms_default: int | None = None
    max_duration_ms_hard: int | None = None
    os_permissions: dict[str, list[str]] = field(default_factory=dict)
    privacy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, permission_id: str, data: dict[str, Any]) -> "HostPermissionDefinition":
        raw_os_permissions = data.get("os_permissions")
        raw_os = raw_os_permissions if isinstance(raw_os_permissions, dict) else {}
        os_permissions = {
            str(platform): [str(item) for item in values if str(item or "").strip()]
            for platform, values in raw_os.items()
            if isinstance(values, list)
        }
        raw_privacy = data.get("privacy")
        privacy = raw_privacy if isinstance(raw_privacy, dict) else {}
        return cls(
            permission_id=permission_id,
            label=str(data.get("label") or permission_id),
            risk_level=str(data.get("risk_level") or "medium"),
            approval_required=bool(data.get("approval_required", True)),
            stream_allowed=bool(data.get("stream_allowed", False)),
            typed_confirmation_required=bool(data.get("typed_confirmation_required", False)),
            max_duration_ms_default=_optional_int(data.get("max_duration_ms_default")),
            max_duration_ms_hard=_optional_int(data.get("max_duration_ms_hard")),
            os_permissions=os_permissions,
            privacy=dict(privacy),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "permission_id": self.permission_id,
            "label": self.label,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "stream_allowed": self.stream_allowed,
            "typed_confirmation_required": self.typed_confirmation_required,
            "max_duration_ms_default": self.max_duration_ms_default,
            "max_duration_ms_hard": self.max_duration_ms_hard,
            "os_permissions": dict(self.os_permissions),
            "privacy": dict(self.privacy),
        }


def _optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
