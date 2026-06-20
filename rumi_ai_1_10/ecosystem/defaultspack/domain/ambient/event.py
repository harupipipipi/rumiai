from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


SOURCE_ALIASES = {
    "mic": "microphone",
    "microphone": "microphone",
    "audio": "microphone",
    "camera": "camera",
    "vision": "camera",
    "webcam": "camera",
    "hook": "hook",
    "external": "hook",
}

TRIGGER_ALIASES = {
    "wake": "voice_wake",
    "wake_voice": "voice_wake",
    "voice": "voice_wake",
    "voice_wake": "voice_wake",
    "transcription_test": "transcription_test",
    "transcribe_test": "transcription_test",
    "speech_test": "transcription_test",
    "pinch": "pinch",
    "gesture_pinch": "pinch",
    "finger_choice": "gesture_choice",
    "gesture_choice": "gesture_choice",
    "choice": "gesture_choice",
    "approval_gesture": "approval_gesture",
    "gesture_approval": "approval_gesture",
    "external_hook": "external_hook",
}


@dataclass(frozen=True)
class AmbientTriggerEvent:
    event_id: str
    source: str
    trigger: str
    mode: str
    action_id: str
    input_text: str
    confidence: float
    duration_ms: int
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AmbientTriggerEvent":
        data = dict(payload if isinstance(payload, dict) else {})
        source = _normalize(SOURCE_ALIASES, data.get("source") or data.get("provider"), "hook")
        trigger = _normalize(TRIGGER_ALIASES, data.get("trigger") or data.get("kind"), "external_hook")
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        return cls(
            event_id=str(data.get("event_id") or data.get("id") or f"ambient_{uuid.uuid4().hex}"),
            source=source,
            trigger=trigger,
            mode=str(data.get("mode") or data.get("intent") or "open_input").strip() or "open_input",
            action_id=str(data.get("action_id") or data.get("action") or "").strip(),
            input_text=str(data.get("input_text") or data.get("text") or data.get("message") or ""),
            confidence=_float(data.get("confidence"), 1.0),
            duration_ms=max(0, int(_float(data.get("duration_ms"), 0))),
            payload=data,
            metadata=dict(metadata),
            created_at=str(data.get("created_at") or _now()),
        )


def _normalize(aliases: dict[str, str], value: Any, default: str) -> str:
    key = str(value or "").strip().lower()
    return aliases.get(key, key or default)


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
