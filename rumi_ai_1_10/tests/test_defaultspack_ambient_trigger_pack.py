from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_ambient_router_requires_enabled_monitor_and_rumi_permissions(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    disabled = router.submit_event(
        {
            "source": "microphone",
            "trigger": "voice_wake",
            "audio_embedding": [1.0, 0.0, 0.0],
        }
    )
    assert disabled["status"] == "ignored"
    assert disabled["reason"] == "ambient_monitor.disabled"

    router.start_monitor()
    denied = router.submit_event(
        {
            "source": "microphone",
            "trigger": "voice_wake",
            "audio_embedding": [1.0, 0.0, 0.0],
        }
    )
    assert denied["status"] == "denied"
    assert set(denied["missing_permissions"]) == {"microphone.capture", "ambient.trigger.dispatch"}


def test_voice_wake_enrolls_first_audio_sample_and_matches_by_embedding(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    router.start_monitor()
    router.grant_permission("microphone.capture", os_status="granted")
    router.grant_permission("camera.capture", os_status="granted")
    router.grant_permission("ambient.trigger.dispatch")

    enrolled = router.submit_event(
        {
            "source": "microphone",
            "trigger": "voice_wake",
            "audio_embedding": [1.0, 0.0, 0.0],
            "wake_phrase": "this text must not be used",
            "metadata": {"audio_blob": "raw-audio", "image_frame": "raw-image"},
        }
    )
    assert enrolled["status"] == "enrolled"
    assert enrolled["reason"] == "voice_wake.first_sample_enrolled"

    rejected = router.submit_event(
        {
            "source": "microphone",
            "trigger": "voice_wake",
            "audio_embedding": [0.0, 1.0, 0.0],
            "wake_phrase": "this text must not be used",
        }
    )
    assert rejected["status"] == "ignored"
    assert rejected["reason"] == "voice_wake.classifier_rejected"

    matched = router.submit_event(
        {
            "source": "microphone",
            "trigger": "voice_wake",
            "audio_embedding": [0.98, 0.02, 0.0],
            "wake_phrase": "different text still matches by audio embedding",
        }
    )
    assert matched["status"] == "open_input"
    assert matched["focus_composer"] is True

    audit_records = [
        json.loads(line)
        for line in (tmp_path / "ambient-audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    forbidden_keys = {"audio_embedding", "wake_phrase", "audio_blob", "image_frame", "dataUrl"}
    assert not _contains_any_key(audit_records, forbidden_keys)


def test_pinch_and_agent_dispatch_share_ambient_router(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    router.start_monitor()
    router.grant_permission("microphone.capture", os_status="granted")
    router.grant_permission("camera.capture", os_status="granted")
    router.grant_permission("ambient.trigger.dispatch")

    pinch_start = router.submit_event(
        {
            "source": "camera",
            "trigger": "pinch",
            "confidence": 0.93,
            "duration_ms": 420,
            "mode": "record_audio_start",
            "metadata": {"hand": "Right", "normalized_distance": 0.21},
        }
    )
    assert pinch_start["status"] == "recording_started"
    assert pinch_start["capture_started"] is True

    with patch("domain.ambient.router.submit_input", return_value={"status": "ok", "assistant_text": ""}) as submit:
        pinch_release = router.submit_event(
            {
                "source": "camera",
                "trigger": "pinch",
                "confidence": 0.94,
                "duration_ms": 900,
                "mode": "dispatch_audio",
                "conversation_id": "conv-1",
                "attachments": [
                    {
                        "name": "pinch.webm",
                        "type": "audio/webm",
                        "size": 1234,
                        "dataUrl": "data:audio/webm;base64,AAAA",
                        "ephemeral": True,
                        "do_not_persist": True,
                    }
                ],
                "metadata": {"hand": "Right", "normalized_distance": 0.42},
            },
            {"conversation_id": "conv-1"},
        )

    assert pinch_release["status"] == "ok"
    envelope = submit.call_args.args[0]
    assert envelope.delivery["action_id"] == "chat.message"
    assert envelope.input.startswith("このpinch中")
    assert envelope.attachments[0]["type"] == "audio/webm"
    assert envelope.attachments[0]["do_not_persist"] is True

    router.submit_event(
        {
            "source": "microphone",
            "trigger": "voice_wake",
            "audio_embedding": [1.0, 0.0, 0.0],
        }
    )
    with patch("domain.ambient.router.submit_input", return_value={"status": "ok", "assistant_text": ""}) as submit:
        dispatched = router.submit_event(
            {
                "source": "microphone",
                "trigger": "voice_wake",
                "audio_embedding": [1.0, 0.0, 0.0],
                "input_text": "delegate this task",
                "action_id": "agent.delegate",
                "conversation_id": "conv-1",
            },
            {"conversation_id": "conv-1"},
        )

    assert dispatched["status"] == "ok"
    envelope = submit.call_args.args[0]
    assert envelope.delivery["action_id"] == "agent.delegate"
    assert envelope.source["provider"] == "ambient"
    assert envelope.target["conversation_id"] == "conv-1"


def test_ambient_routes_and_functions_are_registered():
    from domain.function_runtime.registry import block_module_for, default_args_for, get_spec
    from transport.registry import canonical_http_route_specs

    routes = {(route.method, route.pattern, route.block_module) for route in canonical_http_route_specs()}
    assert ("GET", "/api/ambient/status", "blocks.ambient.status") in routes
    assert ("POST", "/api/ambient/monitor/start", "blocks.ambient.monitor") in routes
    assert ("POST", "/api/ambient/events", "blocks.ambient.event_submit") in routes
    assert block_module_for("ambient_event_submit") == "blocks.ambient.event_submit"
    assert default_args_for("ambient_monitor_stop") == {"action": "stop"}
    assert get_spec("ambient_monitor_start").requires == (
        "microphone.capture",
        "camera.capture",
        "ambient.trigger.dispatch",
    )


def test_rumi_ambient_trigger_pack_metadata_exposes_install_prompt_permissions_and_hooks():
    pack_json = ROOT / "ecosystem" / "setup_pack" / "rumi_ambient_trigger_pack" / "pack.json"
    pack = json.loads(pack_json.read_text(encoding="utf-8"))
    assert pack["supports_all_ok"] is False
    assert pack["required_permissions"] == [
        "microphone.capture",
        "camera.capture",
        "ambient.trigger.dispatch",
    ]
    assert "マイク/カメラ" in pack["install_prompt"]["title"]
    assert {"small_window", "defaultspack_input", "line_hook", "discord_hook", "web_hook"} <= set(pack["install_surfaces"])

    extension_json = ROOT / "ecosystem" / "rumi_ambient_trigger_pack" / "frontend_extensions" / "ambient_trigger.ui.json"
    extension = json.loads(extension_json.read_text(encoding="utf-8"))
    surface_ids = {surface["id"] for surface in extension["surfaces"]}
    assert {"ambient_mini_window", "defaultspack_input", "line_hook", "discord_hook", "web_hook"} <= surface_ids
    assert extension["privacy"]["store_audio"] is False
    assert extension["privacy"]["store_images"] is False


def _contains_any_key(value, keys: set[str]) -> bool:
    if isinstance(value, dict):
        return any(key in keys or _contains_any_key(item, keys) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_any_key(item, keys) for item in value)
    return False
