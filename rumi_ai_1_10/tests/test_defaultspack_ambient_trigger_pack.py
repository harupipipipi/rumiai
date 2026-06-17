from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
MIC_PERMISSION = "host.microphone.capture"
CAMERA_PERMISSION = "host.camera.capture"

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
    assert set(denied["missing_permissions"]) == {MIC_PERMISSION, "ambient.trigger.dispatch"}


def test_voice_wake_enrolls_first_audio_sample_and_matches_by_embedding(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    router.start_monitor()
    router.grant_permission(MIC_PERMISSION, os_status="granted")
    router.grant_permission(CAMERA_PERMISSION, os_status="granted")
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
    router.grant_permission(MIC_PERMISSION, os_status="granted")
    router.grant_permission(CAMERA_PERMISSION, os_status="granted")
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


def test_gesture_choice_does_not_dispatch_numeric_reply_without_audio(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    router.start_monitor()
    router.grant_permission(CAMERA_PERMISSION, os_status="granted")
    router.grant_permission("ambient.trigger.dispatch")

    with patch("domain.ambient.router.submit_input", return_value={"status": "ok", "assistant_text": ""}) as submit:
        ignored = router.submit_event(
            {
                "source": "camera",
                "trigger": "gesture_choice",
                "mode": "choice_response",
                "choice": 3,
                "confidence": 0.96,
                "duration_ms": 3000,
                "conversation_id": "conv-choice",
                "metadata": {"hold_ms": 3000, "pinch_armed": True},
            },
            {"conversation_id": "conv-choice"},
        )

    assert ignored["status"] == "ignored"
    assert ignored["reason"] == "gesture_choice.chat_dispatch_disabled"
    submit.assert_not_called()


def test_ambient_routing_can_create_session_or_per_trigger_chats(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(tmp_path / "conversations.json"))

    from domain.ambient.router import AmbientTriggerRouter
    from domain.chat.store import ChatStore

    router = AmbientTriggerRouter()
    router.start_monitor()
    router.grant_permission(MIC_PERMISSION, os_status="granted")
    router.grant_permission(CAMERA_PERMISSION, os_status="granted")
    router.grant_permission("ambient.trigger.dispatch")
    router.configure({
        "routing": {
            "mode": "startup_new_chat",
            "group_id": "gesture",
            "group_title": "Gesture",
            "model": "opencode-go/kimi-k2.6",
        }
    })

    with patch("domain.ambient.router.submit_input", return_value={"status": "ok", "assistant_text": ""}) as submit:
        first = router.submit_event(_pinch_audio_payload())
        second = router.submit_event(_pinch_audio_payload())

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    first_envelope = submit.call_args_list[0].args[0]
    second_envelope = submit.call_args_list[1].args[0]
    assert first_envelope.target["conversation_id"] == second_envelope.target["conversation_id"]
    created = ChatStore().get_conversation(first_envelope.target["conversation_id"])
    assert created["group_id"] == "gesture"
    assert created["model"] == "opencode-go/kimi-k2.6"

    router.configure({"routing": {"mode": "always_new_chat", "group_id": "gesture"}})
    with patch("domain.ambient.router.submit_input", return_value={"status": "ok", "assistant_text": ""}) as submit:
        router.submit_event(_pinch_audio_payload())
        router.submit_event(_pinch_audio_payload())

    assert submit.call_args_list[0].args[0].target["conversation_id"] != submit.call_args_list[1].args[0].target["conversation_id"]

    router.configure({"routing": {"mode": "always_new_chat", "group_enabled": False, "group_id": "gesture"}})
    with patch("domain.ambient.router.submit_input", return_value={"status": "ok", "assistant_text": ""}) as submit:
        router.submit_event(_pinch_audio_payload())

    ungrouped_id = submit.call_args.args[0].target["conversation_id"]
    ungrouped = ChatStore().get_conversation(ungrouped_id)
    assert ungrouped["group_id"] is None
    assert "group_id" not in ungrouped.get("metadata", {})


def test_selected_chat_routing_passes_saved_model_as_turn_param(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    router.start_monitor()
    router.grant_permission(MIC_PERMISSION, os_status="granted")
    router.grant_permission(CAMERA_PERMISSION, os_status="granted")
    router.grant_permission("ambient.trigger.dispatch")
    router.configure({
        "routing": {
            "mode": "selected_chat",
            "conversation_id": "conv-selected",
            "model": "opencode-go/kimi-k2.6",
        }
    })

    with patch("domain.ambient.router.submit_input", return_value={"status": "ok", "assistant_text": ""}) as submit:
        dispatched = router.submit_event(_pinch_audio_payload(), {"conversation_id": "conv-selected"})

    assert dispatched["status"] == "ok"
    envelope = submit.call_args.args[0]
    assert envelope.target["conversation_id"] == "conv-selected"
    assert envelope.chat["conversation_id"] == "conv-selected"
    assert envelope.params["model"] == "opencode-go/kimi-k2.6"


def test_ai_send_approval_mode_holds_ambient_input_until_server_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    router.grant_permission("ambient.trigger.dispatch")
    router.configure({"routing": {"ai_send_approval_required": True}})

    with patch("domain.ambient.router.submit_input", return_value={"status": "ok", "assistant_text": "hi"}) as submit:
        pending = router.submit_event(
            {
                "source": "hook",
                "trigger": "external_hook",
                "mode": "preset_text",
                "action_id": "chat.message",
                "input_text": "hello",
                "approved": True,
            }
        )

        assert pending["status"] == "approval_required"
        assert pending["reason"] == "ambient.ai_send_approval_required"
        assert pending["client_approved_flag_ignored"] is True
        submit.assert_not_called()

        request_id = pending["approval_request_id"]
        status = router.status()
        assert status["routing"]["ai_send_approval_required"] is True
        assert status["pending_approval"]["request_id"] == request_id
        assert status["pending_approval"]["input_preview"] == "hello"

        approved = router.approve_pending(request_id)

    assert approved["status"] == "ok"
    envelope = submit.call_args.args[0]
    assert envelope.input == "hello"
    assert envelope.delivery["action_id"] == "chat.message"
    assert envelope.metadata["ambient"]["approval_request_id"] == request_id
    assert router.status()["pending_approval"] is None


def test_ai_send_approval_pending_summary_does_not_expose_audio_data(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    router.start_monitor()
    router.grant_permission(MIC_PERMISSION, os_status="granted")
    router.grant_permission(CAMERA_PERMISSION, os_status="granted")
    router.grant_permission("ambient.trigger.dispatch")
    router.configure({"routing": {"ai_send_approval_required": True}})

    with patch("domain.ambient.router.submit_input") as submit:
        pending = router.submit_event(_pinch_audio_payload())

    assert pending["status"] == "approval_required"
    submit.assert_not_called()
    summary = router.status()["pending_approval"]
    assert summary["has_audio"] is True
    assert summary["attachment_count"] == 1
    assert "data:audio" not in json.dumps(summary)
    assert "AAAA" not in json.dumps(summary)


def test_ambient_preset_hello_uses_submit_input_path_without_approval_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    router.grant_permission("ambient.trigger.dispatch")

    with patch("domain.ambient.router.submit_input", return_value={"status": "ok", "assistant_text": "hi"}) as submit:
        result = router.submit_event(
            {
                "source": "hook",
                "trigger": "external_hook",
                "mode": "preset_text",
                "action_id": "chat.message",
                "input_text": "hello",
            }
        )

    assert result["status"] == "ok"
    envelope = submit.call_args.args[0]
    assert envelope.input == "hello"
    assert envelope.source["provider"] == "ambient"
    assert envelope.delivery["action_id"] == "chat.message"


def test_approval_gesture_is_audited_without_dispatch(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    router.start_monitor()
    router.grant_permission(CAMERA_PERMISSION, os_status="granted")
    router.grant_permission("ambient.trigger.dispatch")

    with patch("domain.ambient.router.submit_input") as submit:
        result = router.submit_event(
            {
                "source": "camera",
                "trigger": "approval_gesture",
                "mode": "swipe_reject",
                "decision": "reject",
                "confidence": 0.91,
                "metadata": {"approval_kind": "runtime"},
            }
        )

    assert result["status"] == "approval_intent"
    assert result["decision"] == "reject"
    submit.assert_not_called()


def test_os_permission_check_updates_status_without_granting_rumi_permissions(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    state = router.check_os_permissions({MIC_PERMISSION: "denied", CAMERA_PERMISSION: "granted"})

    assert state["permissions"]["os"][MIC_PERMISSION]["status"] == "denied"
    assert state["permissions"]["os"][CAMERA_PERMISSION]["status"] == "granted"
    assert state["permissions"]["rumi"][MIC_PERMISSION]["granted"] is False
    audit_records = [
        json.loads(line)
        for line in (tmp_path / "ambient-audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert audit_records[-1]["trigger"] == "permission_check"


def test_ambient_permission_function_requires_signed_viewer_operator(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))
    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "test-ambient-secret")

    from blocks.ambient import permissions
    from core_runtime.authority.ui_operator import sign_ui_operator

    unsigned = permissions.run({"action": "grant", "permission_id": MIC_PERMISSION})

    assert unsigned["status"] == "error"
    assert unsigned["error"]["code"] == "AMBIENT_PERMISSION_UI_OPERATOR_REQUIRED"

    signed = permissions.run(
        {
            "action": "grant",
            "permission_id": MIC_PERMISSION,
            "ui_operator": sign_ui_operator("rumi_ambient_trigger_pack", nonce="ambient-grant"),
        }
    )

    assert signed["status"] == "ok"
    assert signed["data"]["permissions"]["rumi"][MIC_PERMISSION]["granted"] is True
    assert signed["data"]["authority"]["request_id"] == "rumi_ambient_trigger_pack"
    assert signed["data"]["authority"]["ui_operator"] is True


def test_ambient_permission_function_rejects_wrong_operator_request(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))
    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "test-ambient-secret")

    from blocks.ambient import permissions
    from core_runtime.authority.ui_operator import sign_ui_operator

    result = permissions.run(
        {
            "action": "grant",
            "permission_id": MIC_PERMISSION,
            "ui_operator": sign_ui_operator("different-request", nonce="ambient-wrong"),
        }
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "AMBIENT_PERMISSION_UI_OPERATOR_REQUIRED"
    assert "request mismatch" in result["error"]["message"]


def test_ambient_permission_check_function_updates_only_os_state_without_operator(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))
    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "test-ambient-secret")

    from blocks.ambient import permissions

    checked = permissions.run(
        {
            "action": "check_os",
            "statuses": {MIC_PERMISSION: "granted", CAMERA_PERMISSION: "denied"},
        }
    )

    assert checked["status"] == "ok"
    assert checked["data"]["permissions"]["os"][MIC_PERMISSION]["status"] == "granted"
    assert checked["data"]["permissions"]["os"][CAMERA_PERMISSION]["status"] == "denied"
    assert checked["data"]["permissions"]["rumi"][MIC_PERMISSION]["granted"] is False
    assert checked["data"]["permissions"]["rumi"][CAMERA_PERMISSION]["granted"] is False


def test_ambient_permission_revoke_function_requires_signed_viewer_operator(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(tmp_path / "ambient-state.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))
    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "test-ambient-secret")

    from blocks.ambient import permissions
    from core_runtime.authority.ui_operator import sign_ui_operator

    grant_operator = sign_ui_operator("rumi_ambient_trigger_pack", nonce="ambient-grant")
    assert permissions.run({"action": "grant", "permission_id": MIC_PERMISSION, "ui_operator": grant_operator})["status"] == "ok"

    unsigned = permissions.run({"action": "revoke", "permission_id": MIC_PERMISSION})

    assert unsigned["status"] == "error"
    assert unsigned["error"]["code"] == "AMBIENT_PERMISSION_UI_OPERATOR_REQUIRED"

    revoked = permissions.run(
        {
            "action": "revoke",
            "permission_id": MIC_PERMISSION,
            "ui_operator": sign_ui_operator("rumi_ambient_trigger_pack", nonce="ambient-revoke"),
        }
    )

    assert revoked["status"] == "ok"
    assert revoked["data"]["permissions"]["rumi"][MIC_PERMISSION]["granted"] is False


def test_ambient_store_migrates_legacy_gesture_release_threshold(monkeypatch, tmp_path):
    state_path = tmp_path / "ambient-state.json"
    state_path.write_text(
        json.dumps({
            "services": {
                "gesture_wake_monitor": {
                    "release_threshold": 0.38,
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(state_path))

    from domain.ambient.store import AmbientStore

    state = AmbientStore().read()

    assert state["services"]["gesture_wake_monitor"]["release_threshold"] == 0.46


def test_ambient_routes_and_functions_are_registered():
    from domain.function_runtime.registry import block_module_for, default_args_for, get_spec
    from transport.registry import canonical_http_route_specs, load_legacy_http_route_allowlist

    routes = {(route.method, route.pattern, route.block_module) for route in canonical_http_route_specs()}
    legacy_routes = load_legacy_http_route_allowlist()
    assert ("GET", "/api/ambient/status", "blocks.ambient.status") in routes
    assert ("POST", "/api/ambient/monitor/start", "blocks.ambient.monitor") in routes
    assert ("POST", "/api/ambient/config", "blocks.ambient.config") in routes
    assert ("POST", "/api/ambient/events", "blocks.ambient.event_submit") in routes
    assert ("POST", "/api/ambient/approval/approve", "blocks.ambient.approval") in routes
    assert ("POST", "/api/ambient/approval/deny", "blocks.ambient.approval") in routes
    assert ("POST", "/api/ambient/approval/approve", "blocks.ambient.approval") in legacy_routes
    assert ("POST", "/api/ambient/approval/deny", "blocks.ambient.approval") in legacy_routes
    assert ("POST", "/api/ambient/permissions/check", "blocks.ambient.permissions") in routes
    assert ("GET", "/host-permissions", "") in routes
    assert block_module_for("ambient_event_submit") == "blocks.ambient.event_submit"
    assert block_module_for("ambient_configure") == "blocks.ambient.config"
    assert default_args_for("ambient_monitor_stop") == {"action": "stop"}
    assert default_args_for("ambient_permission_check") == {"action": "check_os"}
    assert get_spec("ambient_monitor_start").requires == (
        MIC_PERMISSION,
        CAMERA_PERMISSION,
        "ambient.trigger.dispatch",
    )


def test_ambient_monitor_start_function_returns_host_stream_intent(monkeypatch):
    from core_runtime.host_intent import validate_host_intent

    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    main_path = DEFAULTSPACK_ROOT / "functions" / "ambient_monitor_start" / "main.py"
    spec = importlib.util.spec_from_file_location("ambient_monitor_start_main", main_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.run(
        {
            "owner_pack": "rumi_ambient_trigger_pack",
            "function_id": "ambient_monitor_start",
            "conversation_id": "conversation-ambient",
        },
        {"max_duration_ms": 30_000, "sample_rate": 16_000, "channels": 1},
    )
    validation = validate_host_intent(
        result,
        caller_pack_id="rumi_ambient_trigger_pack",
        caller_function_id="ambient_monitor_start",
    )

    assert validation.ok is True
    assert result["type"] == "host_stream_intent"
    assert result["operation"] == MIC_PERMISSION
    assert result["host_function_id"] == "host_microphone_capture"
    assert result["stream"]["enabled"] is True
    assert result["args"]["privacy_mode"] == "audio_embedding_or_ephemeral_recording"
    assert result["consumer"] == {
        "pack_id": "rumi_ambient_trigger_pack",
        "function_id": "ambient_audio_classifier",
    }


def test_rumi_ambient_trigger_pack_metadata_exposes_install_prompt_permissions_and_surfaces():
    pack_json = ROOT / "ecosystem" / "setup_pack" / "rumi_ambient_trigger_pack" / "pack.json"
    pack = json.loads(pack_json.read_text(encoding="utf-8"))
    assert pack["supports_all_ok"] is False
    assert pack["required_permissions"] == [
        MIC_PERMISSION,
        CAMERA_PERMISSION,
        "ambient.trigger.dispatch",
    ]
    assert "マイク/カメラ" in pack["install_prompt"]["title"]
    assert pack["install_surfaces"] == ["small_window", "defaultspack_input"]
    assert "LINE" not in pack["install_prompt"]["surface_question"]
    assert "external_input" not in pack["overlap_policy"]

    extension_json = ROOT / "ecosystem" / "rumi_ambient_trigger_pack" / "frontend_extensions" / "ambient_trigger.ui.json"
    extension = json.loads(extension_json.read_text(encoding="utf-8"))
    surface_ids = {surface["id"] for surface in extension["surfaces"]}
    assert surface_ids == {"ambient_mini_window", "defaultspack_input"}
    assert "LINE" not in extension["install_prompt"]["surface_question"]
    assert extension["privacy"]["store_audio"] is False
    assert extension["privacy"]["store_images"] is False
    assert extension["privacy"]["gesture_choice"]["choices"] == [2, 3, 4]
    assert extension["privacy"]["gesture_choice"]["requires_audio"] is False
    assert extension["privacy"]["gesture_choice"]["profile_mutation"] is False
    assert extension["privacy"]["approval_gesture"]["requires_thumb_index_contact"] is False


def test_ambient_status_hides_legacy_external_hooks(monkeypatch, tmp_path):
    store_path = tmp_path / "ambient-state.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_STORE_PATH", str(store_path))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_AMBIENT_AUDIT_PATH", str(tmp_path / "ambient-audit.jsonl"))
    store_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "defaultspack_input": {"enabled": True, "profile": "defaults.console.input"},
                    "line": {"enabled": True, "profile": "legacy.line"},
                    "discord": {"enabled": True, "profile": "legacy.discord"},
                    "web": {"enabled": True, "profile": "legacy.web"},
                }
            }
        ),
        encoding="utf-8",
    )

    from domain.ambient.router import AmbientTriggerRouter

    router = AmbientTriggerRouter()
    status = router.status()

    assert status["hooks"] == {
        "defaultspack_input": {"enabled": True, "profile": "defaults.console.input"},
    }

    router.start_monitor()
    persisted = json.loads(store_path.read_text(encoding="utf-8"))
    assert persisted["hooks"] == {
        "defaultspack_input": {"enabled": True, "profile": "defaults.console.input"},
    }


def _contains_any_key(value, keys: set[str]) -> bool:
    if isinstance(value, dict):
        return any(key in keys or _contains_any_key(item, keys) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_any_key(item, keys) for item in value)
    return False


def _pinch_audio_payload() -> dict:
    return {
        "source": "camera",
        "trigger": "pinch",
        "confidence": 0.94,
        "duration_ms": 900,
        "mode": "dispatch_audio",
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
    }
