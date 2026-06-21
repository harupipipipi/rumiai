from __future__ import annotations

from typing import Any


def run(context, args):
    payload = dict(args or {}) if isinstance(args, dict) else {}
    runtime_context = dict(context or {}) if isinstance(context, dict) else {}
    max_duration_ms = int(payload.get("max_duration_ms") or payload.get("duration_ms") or 300_000)
    sample_rate = int(payload.get("sample_rate") or 16_000)
    channels = int(payload.get("channels") or 1)
    return {
        "type": "ambient_browser_monitor_contract",
        "version": 1,
        "success": True,
        "status": "browser_owned_monitor",
        "capture_owner": "defaultspack_webapp",
        "contract": {
            "camera": "browser.getUserMedia",
            "microphone": "browser.getUserMedia",
            "trigger": "ok_mark_release_submits_ephemeral_recording",
        },
        "capture_options": {
            "sample_rate": sample_rate,
            "channels": channels,
            "max_duration_ms": max_duration_ms,
            "privacy_mode": "audio_embedding_or_ephemeral_recording",
        },
        "host_stream": {
            "requested": False,
            "available": False,
            "reason": "Viewer host stream capture backend is not advertised; ambient recording is owned by the pack window.",
        },
        "reason": str(payload.get("reason") or "Ambient wake monitoring needs microphone audio.").strip(),
        "caller": {
            "pack_id": _context_value(runtime_context, "owner_pack", "pack_id") or "rumi_ambient_trigger_pack",
            "function_id": _context_value(runtime_context, "function_id") or "ambient_monitor_start",
        },
        "conversation_id": _context_value(runtime_context, "conversation_id", "conversation_turn_id"),
        "consumer": {
            "pack_id": "rumi_ambient_trigger_pack",
            "function_id": "ambient_audio_classifier",
        },
    }


def _context_value(context: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(context.get(key) or "").strip()
        if value:
            return value
    return ""
