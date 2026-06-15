from __future__ import annotations

import importlib.util
import sys
import time
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXPECTED_HOST_MEDIATOR_FUNCTIONS = {
    "host_permission_status": "host.permission.status",
    "host_permission_open_settings": "host.permission.open_settings",
    "host_intent_execute": "host.intent.execute",
    "host_stream_start": "host.stream.start",
    "host_stream_stop": "host.stream.stop",
    "host_screen_capture": "host.screen.capture",
    "host_accessibility_snapshot": "host.accessibility.read",
    "host_accessibility_action": "host.accessibility.mutate",
    "host_input_pointer": "host.input.pointer",
    "host_input_keyboard": "host.input.keyboard",
    "host_clipboard_read": "host.clipboard.read",
    "host_clipboard_write": "host.clipboard.write",
    "host_microphone_capture": "host.microphone.capture",
    "host_audio_output": "host.audio.output",
    "host_speech_transcribe": "host.speech.transcribe",
    "host_speech_synthesize": "host.speech.synthesize",
    "host_camera_capture": "host.camera.capture",
    "host_file_open_dialog": "host.file.open_dialog",
    "host_file_read_selected": "host.file.read_user_selected",
    "host_file_write_selected": "host.file.write_user_selected",
    "host_process_open_url": "host.process.open_url",
    "host_process_launch_app": "host.process.launch_app",
    "host_process_exec_guarded": "host.process.exec_guarded",
}


def test_host_permission_registry_normalizes_ambient_aliases():
    from core_runtime.host_permissions import get_host_permission_definition, normalize_host_permission_id

    assert normalize_host_permission_id("microphone.capture") == "host.microphone.capture"
    assert normalize_host_permission_id("camera.capture") == "host.camera.capture"
    assert get_host_permission_definition("host.microphone.capture").stream_allowed is True
    assert get_host_permission_definition("host.process.exec_guarded").typed_confirmation_required is True


def test_host_intent_validator_enforces_typed_operations_and_stream_rules():
    from core_runtime.host_intent import validate_host_intent

    ok = validate_host_intent(
        {
            "type": "host_stream_intent",
            "operation": "microphone.capture",
            "stream": {"enabled": True, "max_duration_ms": 5_000},
        },
        caller_pack_id="pack.voice",
        caller_function_id="listen",
    )
    rejected = validate_host_intent(
        {
            "type": "host_stream_intent",
            "operation": "host.clipboard.read",
            "stream": {"enabled": True},
        },
        caller_pack_id="pack.clipboard",
        caller_function_id="read",
    )
    unknown = validate_host_intent(
        {"type": "host_intent", "operation": "host.unknown.magic"},
        caller_pack_id="pack.bad",
        caller_function_id="do",
    )

    assert ok.ok is True
    assert ok.intent.operation == "host.microphone.capture"
    assert rejected.ok is False
    assert any("does not allow streams" in error for error in rejected.errors)
    assert unknown.ok is False
    assert any("unknown host operation" in error for error in unknown.errors)


def test_default_builtin_grants_allow_host_pack_but_not_exec_guarded(tmp_path):
    from core_runtime.bootstrap.default_builtin_grants import apply_default_builtin_grants
    from core_runtime.capability_grant_manager import CapabilityGrantManager

    grants = CapabilityGrantManager(
        grants_dir=str(tmp_path / "capabilities"),
        secret_key="capability-test-key-" + ("h" * 32),
    )
    apply_default_builtin_grants(grants)

    host_pack = grants.get_grant("rumi_host_capabilities_pack")
    authority_window = grants.get_grant("system:authority-approval-window")

    assert host_pack is not None
    assert "host.microphone.capture" in host_pack.permissions
    assert "host.camera.capture" in host_pack.permissions
    assert "host.process.exec_guarded" not in host_pack.permissions
    assert authority_window is not None
    assert "authority.request.approve" in authority_window.permissions


def test_host_capabilities_pack_contract_names_boundary_and_privacy():
    ecosystem = json.loads((ROOT / "ecosystem" / "rumi_host_capabilities_pack" / "ecosystem.json").read_text())
    setup = json.loads((ROOT / "ecosystem" / "setup_pack" / "rumi_host_capabilities_pack" / "pack.json").read_text())

    assert ecosystem["pack_id"] == "rumi_host_capabilities_pack"
    assert ecosystem["security_boundary"]["defaultspack_role"] == "ui_orchestration_and_authority_only"
    assert ecosystem["security_boundary"]["ordinary_pack_contract"] == "return_host_intent_json"
    assert "host.process.exec_guarded" in ecosystem["default_grants"]["exclude"]
    assert ecosystem["privacy"]["store_microphone_audio"] is False
    assert ecosystem["privacy"]["store_camera_frames"] is False
    assert setup["overlap_policy"]["defaultspack_host_execution"] == "forbidden"


def test_host_capabilities_pack_defines_standard_mediator_functions():
    pack_root = ROOT / "ecosystem" / "rumi_host_capabilities_pack"
    ecosystem = json.loads((pack_root / "ecosystem.json").read_text())
    assert ecosystem["host_functions"] == {
        function_id: {
            "operation": operation,
            "stream": operation in {"host.stream.start", "host.microphone.capture", "host.speech.transcribe", "host.camera.capture", "host.process.exec_guarded"},
            "executor_owner": "rumi_viewer_host_broker",
        }
        for function_id, operation in sorted(EXPECTED_HOST_MEDIATOR_FUNCTIONS.items())
    }
    for function_id, operation in EXPECTED_HOST_MEDIATOR_FUNCTIONS.items():
        function_dir = pack_root / "functions" / function_id
        manifest = json.loads((function_dir / "manifest.json").read_text())
        assert (function_dir / "main.py").is_file()
        assert manifest["function_id"] == function_id
        assert manifest["host_execution"] is False
        assert manifest["calling_convention"] == "subprocess"
        assert manifest["requires_approval"] is True
        assert manifest["caller_requires"] == ["user.approved.high_risk"]
        assert operation in manifest["requires"]
        assert manifest["host_operation"]["operation"] == operation
        if operation == "host.process.exec_guarded":
            assert manifest["risk_level"] == "critical"
            assert manifest["host_operation"]["typed_confirmation_required"] is True


def test_host_mediator_function_returns_valid_host_intent(monkeypatch):
    from core_runtime.host_intent import validate_host_intent

    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    main_path = (
        ROOT
        / "ecosystem"
        / "rumi_host_capabilities_pack"
        / "functions"
        / "host_microphone_capture"
        / "main.py"
    )
    spec = importlib.util.spec_from_file_location("host_microphone_capture_main", main_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.run(
        {
            "owner_pack": "rumi_ambient_trigger_pack",
            "function_id": "ambient_monitor_start",
            "conversation_id": "conversation-1",
        },
        {
            "duration_ms": 1000,
            "stream": {"enabled": True, "max_duration_ms": 1000},
            "approval_token": "not-forwarded",
            "reason": "wake audio",
        },
    )
    validation = validate_host_intent(
        result,
        caller_pack_id="fallback_pack",
        caller_function_id="fallback_function",
    )

    assert result["type"] == "host_stream_intent"
    assert result["operation"] == "host.microphone.capture"
    assert result["host_function_id"] == "host_microphone_capture"
    assert result["caller"]["pack_id"] == "rumi_ambient_trigger_pack"
    assert result["caller"]["function_id"] == "ambient_monitor_start"
    assert result["conversation_id"] == "conversation-1"
    assert "approval_token" not in result["args"]
    assert validation.ok is True


def test_direct_host_function_from_non_host_pack_becomes_critical_authority_request(monkeypatch):
    from core_runtime.authority.models import AuthorityDecision
    from core_runtime.capability_executor import CapabilityExecutor

    class Authority:
        calls: list[dict] = []

        def check(self, **kwargs):
            self.calls.append(kwargs)
            return AuthorityDecision(
                allowed=False,
                permission_id=kwargs["permission_id"],
                principal_id=kwargs["principal_id"],
                reason="host boundary",
                request_id="auth-host-1",
                approval_required=True,
                risk_level="critical",
                resource=kwargs["resource"],
            )

    authority = Authority()
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: authority)
    executor = CapabilityExecutor()
    entry = SimpleNamespace(
        pack_id="third_party_pack",
        function_id="run_shell",
        qualified_name="third_party_pack.run_shell",
        calling_convention="python_host",
        host_execution=True,
        manifest={"host_operation": "shell.exec"},
    )

    response = executor._host_boundary_response_if_needed(
        entry=entry,
        principal_id="third_party_pack",
        request_id="req-host",
        start_time=time.time(),
    )

    assert response is not None
    assert response.success is False
    assert response.error_type == "critical_host_confirmation_required"
    assert response.output["approval_kind"] == "critical_host_function"
    assert response.output["request_id"] == "auth-host-1"
    assert response.output["permission_id"] == "host.process.exec_guarded"
    assert response.output["typed_confirmation_required"] is True
    assert authority.calls[0]["permission_id"] == "host.process.exec_guarded"


def test_host_capabilities_pack_direct_host_functions_are_exempt_from_extra_boundary():
    from core_runtime.capability_executor import CapabilityExecutor

    executor = CapabilityExecutor()
    entry = SimpleNamespace(
        pack_id="rumi_host_capabilities_pack",
        function_id="microphone_capture",
        qualified_name="rumi_host_capabilities_pack.microphone_capture",
        calling_convention="python_host",
        host_execution=True,
        manifest={"host_operation": "host.microphone.capture"},
    )

    response = executor._host_boundary_response_if_needed(
        entry=entry,
        principal_id="rumi_host_capabilities_pack",
        request_id="req-host",
        start_time=time.time(),
    )

    assert response is None
