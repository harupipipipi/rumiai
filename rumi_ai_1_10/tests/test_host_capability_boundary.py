from __future__ import annotations

import importlib.util
import sys
import time
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _host_mediator_generator():
    generator_path = (
        ROOT
        / "ecosystem"
        / "rumi_host_capabilities_pack"
        / "scripts"
        / "generate_host_mediator_functions.py"
    )
    spec = importlib.util.spec_from_file_location("generate_host_mediator_functions", generator_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _host_permission_registry() -> dict[str, dict]:
    return json.loads((ROOT / "core_runtime" / "host_permissions" / "default_registry.json").read_text())


def _host_function_id_for_operation(operation: str) -> str:
    return _host_mediator_generator().host_function_id_for_operation(operation)


def _expected_host_mediator_functions() -> dict[str, str]:
    return _host_mediator_generator().expected_host_mediator_functions(_host_permission_registry())


class _HmacKey:
    def get_active_key(self) -> str:
        return "host-boundary-authority-test-key-" + ("x" * 32)


def _authority_service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUMI_AUTHORITY_MODE", "enforce")
    monkeypatch.setenv("RUMI_PANEL_BOOTSTRAP_SECRET", "panel-bootstrap-test-secret-" + ("p" * 32))
    from core_runtime.authority.request_store import AuthorityRequestStore
    from core_runtime.authority.service import AuthorityService

    store = AuthorityRequestStore(tmp_path / "authority", hmac_key_manager=_HmacKey())
    return AuthorityService(request_store=store)


def _ui_operator(request_id: str):
    from core_runtime.authority.ui_operator import sign_ui_operator

    return sign_ui_operator(request_id, nonce="nonce-" + request_id)


def _direct_host_entry():
    return SimpleNamespace(
        pack_id="third_party_pack",
        function_id="run_shell",
        qualified_name="third_party_pack.run_shell",
        permission_id="third_party_pack.run_shell",
        calling_convention="python_host",
        host_execution=True,
        manifest={"host_operation": "shell.exec"},
        vocab_aliases=[],
        requires=[],
        caller_requires=[],
        function_dir=None,
        main_py_path=None,
        entrypoint="main.py:run",
        is_builtin=False,
    )


def _authority_context(permission_id: str, request_id: str, token: str) -> dict:
    return {
        "authority": {
            "approval_tokens": {
                permission_id: {
                    "request_id": request_id,
                    "approval_token": token,
                    "permission_id": permission_id,
                }
            }
        }
    }


def _executor_for_direct_host_retry():
    from core_runtime.capability_executor import CapabilityExecutor, CapabilityResponse

    executor = CapabilityExecutor()
    executor._initialized = True
    executor._approval_manager = None
    executor._audit = lambda *args, **kwargs: None
    executor._check_entry_trust = lambda *args, **kwargs: None
    executor._is_trusted_builtin_pack = lambda *args, **kwargs: True
    executor._trusted_builtin_pack_path_verdict = lambda *args, **kwargs: True
    executor._is_core_builtin_trust_bypass_entry = lambda *args, **kwargs: False
    executor._grant_manager = SimpleNamespace(
        check=lambda *args, **kwargs: SimpleNamespace(allowed=True, reason="granted", config={})
    )
    executor._execute_host_function = lambda **kwargs: CapabilityResponse(
        success=True,
        output={"executed": True},
        latency_ms=0,
    )
    return executor


def _host_mediator_main_template(function_id: str, operation: str, stream_allowed: bool) -> str:
    return _host_mediator_generator().render_host_mediator_main(function_id, operation, stream_allowed)


def test_host_permission_registry_normalizes_ambient_aliases():
    from core_runtime.host_permissions import get_host_permission_definition, normalize_host_permission_id

    assert normalize_host_permission_id("microphone.capture") == "host.microphone.capture"
    assert normalize_host_permission_id("camera.capture") == "host.camera.capture"
    assert get_host_permission_definition("host.microphone.capture").stream_allowed is False
    assert get_host_permission_definition("host.permission.status").broker_runner_implemented is True
    assert get_host_permission_definition("host.process.exec_guarded").typed_confirmation_required is True


def test_authority_and_frontend_host_permission_definitions_follow_canonical_registry():
    from core_runtime.authority.models import AUTHORITY_PERMISSION_IDS
    from core_runtime.host_permissions.models import HOST_PERMISSION_IDS

    registry = _host_permission_registry()
    frontend_registry = json.loads(
        (
            ROOT
            / "ecosystem"
            / "defaultspack"
            / "webapp"
            / "src"
            / "hostPermissions"
            / "hostPermissionRegistry.json"
        ).read_text(encoding="utf-8")
    )

    assert set(registry) == HOST_PERMISSION_IDS
    assert HOST_PERMISSION_IDS <= AUTHORITY_PERMISSION_IDS
    assert frontend_registry == registry


def test_host_intent_validator_enforces_typed_operations_and_stream_rules():
    from core_runtime.host_intent import validate_host_intent

    ok = validate_host_intent(
        {
            "type": "host_intent",
            "operation": "host.permission.status",
        },
        caller_pack_id="pack.permissions",
        caller_function_id="status",
    )
    stream_rejected = validate_host_intent(
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
    spoofed_pack = validate_host_intent(
        {
            "type": "host_intent",
            "operation": "host.microphone.capture",
            "caller": {"pack_id": "pack.attacker", "function_id": "listen"},
        },
        caller_pack_id="pack.voice",
        caller_function_id="listen",
    )
    spoofed_function = validate_host_intent(
        {
            "type": "host_intent",
            "operation": "host.microphone.capture",
            "caller": {"pack_id": "pack.voice", "function_id": "borrowed_function"},
        },
        caller_pack_id="pack.voice",
        caller_function_id="listen",
    )

    assert ok.ok is True
    assert ok.intent.operation == "host.permission.status"
    assert stream_rejected.ok is False
    assert any("does not allow streams" in error for error in stream_rejected.errors)
    assert rejected.ok is False
    assert any("does not allow streams" in error for error in rejected.errors)
    assert unknown.ok is False
    assert any("unknown host operation" in error for error in unknown.errors)
    assert spoofed_pack.ok is False
    assert any("caller pack id does not match" in error for error in spoofed_pack.errors)
    assert spoofed_function.ok is False
    assert any("caller function id does not match" in error for error in spoofed_function.errors)


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
    assert "host.permission.status" in host_pack.permissions
    assert "host.permission.open_settings" in host_pack.permissions
    assert "host.microphone.capture" not in host_pack.permissions
    assert "host.camera.capture" not in host_pack.permissions
    assert "host.process.exec_guarded" not in host_pack.permissions
    assert authority_window is not None
    assert "authority.request.approve" in authority_window.permissions


def test_host_capabilities_pack_contract_names_boundary_and_privacy():
    ecosystem = json.loads(
        (ROOT / "ecosystem" / "rumi_host_capabilities_pack" / "ecosystem.json").read_text(
            encoding="utf-8"
        )
    )
    setup = json.loads(
        (
            ROOT / "ecosystem" / "setup_pack" / "rumi_host_capabilities_pack" / "pack.json"
        ).read_text(encoding="utf-8")
    )

    assert ecosystem["pack_id"] == "rumi_host_capabilities_pack"
    assert ecosystem["security_boundary"]["defaultspack_role"] == "ui_orchestration_and_authority_only"
    assert ecosystem["security_boundary"]["ordinary_pack_contract"] == "return_host_intent_json"
    assert ecosystem["default_grants"]["include"] == "implemented_host_permissions"
    assert ecosystem["default_grants"]["exclude"] == []
    assert ecosystem["privacy"]["store_microphone_audio"] is False
    assert ecosystem["privacy"]["store_camera_frames"] is False
    assert setup["overlap_policy"]["defaultspack_host_execution"] == "forbidden"


def test_host_capabilities_pack_registry_grants_follow_canonical_host_registry():
    from core_runtime.bootstrap import default_builtin_grants

    registry = _host_permission_registry()
    ecosystem = json.loads((ROOT / "ecosystem" / "rumi_host_capabilities_pack" / "ecosystem.json").read_text())

    implemented = [
        permission_id
        for permission_id, definition in registry.items()
        if definition.get("broker_runner_implemented") is True
    ]
    assert ecosystem["capabilities"] == implemented
    assert ecosystem["default_grants"]["include"] == "implemented_host_permissions"
    assert ecosystem["default_grants"]["exclude"] == []
    assert default_builtin_grants.HOST_CAPABILITIES_PACK_PERMISSIONS == (
        "function.call",
        *(
            permission_id
            for permission_id, definition in registry.items()
            if definition.get("broker_runner_implemented") is True
        ),
    )


def test_host_capabilities_pack_defines_standard_mediator_functions():
    pack_root = ROOT / "ecosystem" / "rumi_host_capabilities_pack"
    registry = _host_permission_registry()
    ecosystem = json.loads((pack_root / "ecosystem.json").read_text())
    expected_functions = _expected_host_mediator_functions()
    generator = _host_mediator_generator()

    assert generator.check_generated_files() == []
    assert ecosystem["host_functions"] == {
        function_id: {
            "operation": operation,
            "stream": bool(registry[operation].get("stream_allowed")),
            "executor_owner": "rumi_viewer_host_broker",
        }
        for function_id, operation in sorted(expected_functions.items())
    }
    for function_id, operation in expected_functions.items():
        function_dir = pack_root / "functions" / function_id
        manifest = json.loads((function_dir / "manifest.json").read_text())
        main_path = function_dir / "main.py"
        assert main_path.is_file()
        assert main_path.read_text() == _host_mediator_main_template(
            function_id,
            operation,
            bool(registry[operation].get("stream_allowed")),
        )
        assert manifest["function_id"] == function_id
        assert manifest["host_execution"] is False
        assert manifest["calling_convention"] == "subprocess"
        approval_required = bool(registry[operation].get("approval_required", True))
        assert manifest["requires_approval"] is approval_required
        assert manifest["caller_requires"] == (["user.approved.high_risk"] if approval_required else [])
        assert operation in manifest["requires"]
        assert manifest["risk"] == registry[operation]["risk_level"]
        assert manifest["risk_level"] == registry[operation]["risk_level"]
        assert manifest["host_operation"]["operation"] == operation
        assert manifest["host_operation"]["stream_allowed"] is bool(
            registry[operation].get("stream_allowed")
        )
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
        / "host_permission_status"
        / "main.py"
    )
    spec = importlib.util.spec_from_file_location("host_permission_status_main", main_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.run(
        {
            "owner_pack": "rumi_ambient_trigger_pack",
            "function_id": "ambient_permission_check",
            "conversation_id": "conversation-1",
        },
        {
            "permission_id": "host.camera.capture",
            "stream": {"enabled": True, "max_duration_ms": 1000},
            "approval_token": "not-forwarded",
            "reason": "permission status",
        },
    )
    validation = validate_host_intent(
        result,
        caller_pack_id="rumi_ambient_trigger_pack",
        caller_function_id="ambient_permission_check",
    )

    assert result["type"] == "host_intent"
    assert result["operation"] == "host.permission.status"
    assert result["stream"]["enabled"] is False
    assert result["stream"]["rejected_reason"] == "operation_does_not_allow_stream"
    assert result["host_function_id"] == "host_permission_status"
    assert result["caller"]["pack_id"] == "rumi_ambient_trigger_pack"
    assert result["caller"]["function_id"] == "ambient_permission_check"
    assert result["conversation_id"] == "conversation-1"
    assert "approval_token" not in result["args"]
    assert validation.ok is True


def test_capability_executor_uses_trusted_host_intent_caller_context():
    from core_runtime.capability_executor import CapabilityExecutor

    executor = CapabilityExecutor()
    ambient_entry = SimpleNamespace(
        pack_id="defaultspack",
        function_id="ambient_monitor_start",
    )
    host_facade_entry = SimpleNamespace(
        pack_id="rumi_host_capabilities_pack",
        function_id="host_permission_status",
    )
    ordinary_entry = SimpleNamespace(
        pack_id="ordinary_pack",
        function_id="ordinary_function",
    )

    assert executor._host_intent_caller_ids(ambient_entry, None) == (
        "rumi_ambient_trigger_pack",
        "ambient_monitor_start",
    )
    assert executor._host_intent_caller_ids(
        host_facade_entry,
        {"owner_pack": "rumi_ambient_trigger_pack", "function_id": "ambient_permission_check"},
    ) == ("rumi_ambient_trigger_pack", "ambient_permission_check")
    assert executor._host_intent_caller_ids(ordinary_entry, {"owner_pack": "spoofed"}) == (
        "ordinary_pack",
        "ordinary_function",
    )


def test_host_intent_executor_dispatches_approved_status_to_viewer_broker(monkeypatch):
    from core_runtime.authority.models import AuthorityDecision
    from core_runtime.host_intent import executor as host_intent_executor
    from core_runtime.host_intent.executor import HostIntentExecutor
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient
    from ecosystem.defaultspack.domain.safety import approval

    captured: dict[str, object] = {}
    authority_checks: list[dict] = []

    class Authority:
        def check(self, **kwargs):
            authority_checks.append(kwargs)
            captured["authority_check"] = kwargs
            return AuthorityDecision(
                allowed=True,
                permission_id=kwargs["permission_id"],
                principal_id=kwargs["principal_id"],
                reason="approved",
                risk_level="high",
                resource=kwargs["resource"],
            )

    class FakeClient:
        def available(self):
            return True

        def execute_intent(self, payload):
            captured["broker_payload"] = dict(payload)
            return {"ok": True, "result": {"permission_id": "host.camera.capture", "status": "unknown"}}

    def fake_issue_execution_token(request_id, args_hash, **kwargs):
        captured["execution_token"] = {
            "request_id": request_id,
            "args_hash": args_hash,
            **kwargs,
        }
        return "viewer-execution-token"

    monkeypatch.setattr(host_intent_executor, "get_authority_service", lambda: Authority())
    monkeypatch.setattr(ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))
    monkeypatch.setattr(approval, "issue_execution_token", fake_issue_execution_token)

    result = HostIntentExecutor().handle(
        {
            "type": "host_intent",
            "operation": "host.permission.status",
            "args": {"permission_id": "host.camera.capture"},
            "caller": {
                "pack_id": "rumi_ambient_trigger_pack",
                "function_id": "ambient_permission_check",
            },
            "host_function_id": "host_permission_status",
        },
        principal_id="rumi_ambient_trigger_pack",
        caller_pack_id="rumi_ambient_trigger_pack",
        caller_function_id="ambient_permission_check",
        request_context={
            "conversation_id": "conv-1",
            "authority": {
                "permission_id": "host.permission.status",
                "request_id": "auth-1",
                "approval_token": "authority-token",
            },
        },
    )

    assert result["success"] is True
    assert result["status"] == "executed"
    assert result["host_broker"]["result"]["permission_id"] == "host.camera.capture"
    assert captured["broker_payload"]["approval_token"] == "viewer-execution-token"
    assert result["host_intent"].get("approval_token") is None
    assert captured["execution_token"]["request_id"] == "auth-1"
    assert captured["execution_token"]["operation"] == "host.permission.status"
    assert captured["execution_token"]["function_id"] == "host_permission_status"
    assert captured["execution_token"]["pack_id"] == "rumi_ambient_trigger_pack"
    assert captured["execution_token"]["conversation_id"] == "conv-1"
    assert [item.get("consume_approval_token") for item in authority_checks] == [False, True]


def test_host_intent_exec_guarded_has_confirmation_phrase_and_approves(tmp_path, monkeypatch):
    from core_runtime.host_intent.executor import HostIntentExecutor

    service = _authority_service(tmp_path, monkeypatch)
    monkeypatch.setattr("core_runtime.host_intent.executor.get_authority_service", lambda: service)
    payload = {
        "type": "host_intent",
        "operation": "host.process.exec_guarded",
        "args": {"argv": ["/bin/echo", "hello"]},
        "caller": {
            "pack_id": "third_party_pack",
            "function_id": "run_shell",
        },
        "host_function_id": "host_process_exec_guarded",
    }

    first = HostIntentExecutor().handle(
        payload,
        principal_id="third_party_pack",
        caller_pack_id="third_party_pack",
        caller_function_id="run_shell",
        request_context={"conversation_id": "conv-1"},
    )

    assert first["status"] == "approval_required"
    phrase = first["resource"]["confirmation_phrase"]
    assert phrase.startswith("RUMI-HOST-")
    assert first["confirmation_phrase"] == phrase
    request_view = service.get_request(first["request_id"])["request"]
    assert request_view["resource"]["confirmation_phrase"] == phrase
    assert request_view["display_metadata"]["confirmation_phrase"] == phrase

    approved = service.approve_request(
        first["request_id"],
        scope="once",
        config={"confirmation_text": phrase},
        ui_operator=_ui_operator(first["request_id"]),
    )
    assert approved["success"] is True

    retry = HostIntentExecutor().handle(
        payload,
        principal_id="third_party_pack",
        caller_pack_id="third_party_pack",
        caller_function_id="run_shell",
        request_context={
            "conversation_id": "conv-1",
            **_authority_context("host.process.exec_guarded", first["request_id"], approved["token"]),
        },
    )

    assert retry["success"] is False
    assert retry["status"] == "host_broker_unavailable"
    assert retry["error_type"] == "host_broker_unavailable"

    retry_again = HostIntentExecutor().handle(
        payload,
        principal_id="third_party_pack",
        caller_pack_id="third_party_pack",
        caller_function_id="run_shell",
        request_context={
            "conversation_id": "conv-1",
            **_authority_context("host.process.exec_guarded", first["request_id"], approved["token"]),
        },
    )

    assert retry_again["success"] is False
    assert retry_again["status"] == "host_broker_unavailable"


def test_host_intent_broker_error_does_not_consume_authority_token(tmp_path, monkeypatch):
    from core_runtime.host_intent.executor import HostIntentExecutor
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient
    from ecosystem.defaultspack.domain.safety import approval

    service = _authority_service(tmp_path, monkeypatch)
    monkeypatch.setattr("core_runtime.host_intent.executor.get_authority_service", lambda: service)

    class FailingBroker:
        def available(self):
            return True

        def execute_intent(self, payload):
            raise RuntimeError("viewer broker http 503")

    monkeypatch.setattr(ViewerBrokerClient, "from_environment", classmethod(lambda cls: FailingBroker()))
    monkeypatch.setattr(approval, "issue_execution_token", lambda *args, **kwargs: "viewer-execution-token")

    payload = {
        "type": "host_intent",
        "operation": "host.process.exec_guarded",
        "args": {"argv": ["/bin/echo", "hello"]},
        "caller": {
            "pack_id": "third_party_pack",
            "function_id": "run_shell",
        },
        "host_function_id": "host_process_exec_guarded",
    }
    first = HostIntentExecutor().handle(
        payload,
        principal_id="third_party_pack",
        caller_pack_id="third_party_pack",
        caller_function_id="run_shell",
        request_context={"conversation_id": "conv-1"},
    )
    phrase = first["confirmation_phrase"]
    approved = service.approve_request(
        first["request_id"],
        scope="once",
        config={"confirmation_text": phrase},
        ui_operator=_ui_operator(first["request_id"]),
    )

    context = {
        "conversation_id": "conv-1",
        **_authority_context("host.process.exec_guarded", first["request_id"], approved["token"]),
    }
    failed = HostIntentExecutor().handle(
        payload,
        principal_id="third_party_pack",
        caller_pack_id="third_party_pack",
        caller_function_id="run_shell",
        request_context=context,
    )
    failed_again = HostIntentExecutor().handle(
        payload,
        principal_id="third_party_pack",
        caller_pack_id="third_party_pack",
        caller_function_id="run_shell",
        request_context=context,
    )

    assert failed["status"] == "host_broker_error"
    assert failed["success"] is False
    assert failed_again["status"] == "host_broker_error"
    assert failed_again["success"] is False


def test_host_intent_executor_fails_closed_without_viewer_broker(monkeypatch):
    from core_runtime.authority.models import AuthorityDecision
    from core_runtime.host_intent import executor as host_intent_executor
    from core_runtime.host_intent.executor import HostIntentExecutor
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    class Authority:
        def check(self, **kwargs):
            return AuthorityDecision(
                allowed=True,
                permission_id=kwargs["permission_id"],
                principal_id=kwargs["principal_id"],
                reason="approved",
                risk_level="high",
                resource=kwargs["resource"],
            )

    class MissingBroker:
        def available(self):
            return False

    monkeypatch.setattr(host_intent_executor, "get_authority_service", lambda: Authority())
    monkeypatch.setattr(ViewerBrokerClient, "from_environment", classmethod(lambda cls: MissingBroker()))

    result = HostIntentExecutor().handle(
        {
            "type": "host_intent",
            "operation": "host.permission.status",
            "args": {},
            "caller": {
                "pack_id": "rumi_ambient_trigger_pack",
                "function_id": "ambient_monitor_start",
            },
        },
        principal_id="rumi_ambient_trigger_pack",
        caller_pack_id="rumi_ambient_trigger_pack",
        caller_function_id="ambient_monitor_start",
        request_context={"conversation_id": "conv-1"},
    )

    assert result["success"] is False
    assert result["status"] == "host_broker_unavailable"
    assert result["error_type"] == "host_broker_unavailable"
    assert result["host_broker"] == {"available": False}


def test_host_intent_executor_fails_closed_when_broker_module_import_fails(monkeypatch):
    from core_runtime.authority.models import AuthorityDecision
    from core_runtime.host_intent import executor as host_intent_executor
    from core_runtime.host_intent.executor import HostIntentExecutor

    class Authority:
        def check(self, **kwargs):
            return AuthorityDecision(
                allowed=True,
                permission_id=kwargs["permission_id"],
                principal_id=kwargs["principal_id"],
                reason="approved",
                risk_level="high",
                resource=kwargs["resource"],
            )

    real_import_module = host_intent_executor.importlib.import_module

    def fake_import_module(name):
        if name.endswith("viewer_broker_client"):
            raise ImportError("viewer broker client missing")
        return real_import_module(name)

    monkeypatch.setattr(host_intent_executor, "get_authority_service", lambda: Authority())
    monkeypatch.setattr(host_intent_executor.importlib, "import_module", fake_import_module)

    result = HostIntentExecutor().handle(
        {
            "type": "host_intent",
            "operation": "host.permission.status",
            "args": {},
            "caller": {
                "pack_id": "rumi_ambient_trigger_pack",
                "function_id": "ambient_monitor_start",
            },
        },
        principal_id="rumi_ambient_trigger_pack",
        caller_pack_id="rumi_ambient_trigger_pack",
        caller_function_id="ambient_monitor_start",
        request_context={"conversation_id": "conv-1"},
    )

    assert result["success"] is False
    assert result["status"] == "host_broker_initialization_failed"
    assert result["error_type"] == "host_broker_initialization_failed"
    assert result["host_broker"]["available"] is False
    assert result["host_broker"]["initialization_error"] == "broker_modules_import_failed"


def test_host_intent_executor_fails_closed_when_approval_module_import_fails(monkeypatch):
    from core_runtime.authority.models import AuthorityDecision
    from core_runtime.host_intent import executor as host_intent_executor
    from core_runtime.host_intent.executor import HostIntentExecutor

    class Authority:
        def check(self, **kwargs):
            return AuthorityDecision(
                allowed=True,
                permission_id=kwargs["permission_id"],
                principal_id=kwargs["principal_id"],
                reason="approved",
                risk_level="high",
                resource=kwargs["resource"],
            )

    real_import_module = host_intent_executor.importlib.import_module

    def fake_import_module(name):
        if name.endswith("safety.approval"):
            raise ImportError("approval token module missing")
        return real_import_module(name)

    monkeypatch.setattr(host_intent_executor, "get_authority_service", lambda: Authority())
    monkeypatch.setattr(host_intent_executor.importlib, "import_module", fake_import_module)

    result = HostIntentExecutor().handle(
        {
            "type": "host_intent",
            "operation": "host.permission.status",
            "args": {},
            "caller": {
                "pack_id": "rumi_ambient_trigger_pack",
                "function_id": "ambient_monitor_start",
            },
        },
        principal_id="rumi_ambient_trigger_pack",
        caller_pack_id="rumi_ambient_trigger_pack",
        caller_function_id="ambient_monitor_start",
        request_context={"conversation_id": "conv-1"},
    )

    assert result["success"] is False
    assert result["status"] == "host_broker_initialization_failed"
    assert result["error_type"] == "host_broker_initialization_failed"
    assert result["host_broker"]["available"] is False
    assert result["host_broker"]["initialization_error"] == "broker_modules_import_failed"


def test_host_intent_executor_fails_closed_when_broker_class_is_missing(monkeypatch):
    from core_runtime.authority.models import AuthorityDecision
    from core_runtime.host_intent import executor as host_intent_executor
    from core_runtime.host_intent.executor import HostIntentExecutor

    class Authority:
        def check(self, **kwargs):
            return AuthorityDecision(
                allowed=True,
                permission_id=kwargs["permission_id"],
                principal_id=kwargs["principal_id"],
                reason="approved",
                risk_level="high",
                resource=kwargs["resource"],
            )

    real_import_module = host_intent_executor.importlib.import_module

    def fake_import_module(name):
        if name.endswith("viewer_broker_client"):
            return SimpleNamespace()
        return real_import_module(name)

    monkeypatch.setattr(host_intent_executor, "get_authority_service", lambda: Authority())
    monkeypatch.setattr(host_intent_executor.importlib, "import_module", fake_import_module)

    result = HostIntentExecutor().handle(
        {
            "type": "host_intent",
            "operation": "host.permission.status",
            "args": {},
            "caller": {
                "pack_id": "rumi_ambient_trigger_pack",
                "function_id": "ambient_monitor_start",
            },
        },
        principal_id="rumi_ambient_trigger_pack",
        caller_pack_id="rumi_ambient_trigger_pack",
        caller_function_id="ambient_monitor_start",
        request_context={"conversation_id": "conv-1"},
    )

    assert result["success"] is False
    assert result["status"] == "host_broker_initialization_failed"
    assert result["error_type"] == "host_broker_initialization_failed"
    assert result["host_broker"]["available"] is False
    assert result["host_broker"]["initialization_error"] == "viewer_broker_client_missing"


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


def test_direct_host_boundary_consumes_approved_retry_token(tmp_path, monkeypatch):
    from core_runtime.capability_executor import CapabilityExecutor

    service = _authority_service(tmp_path, monkeypatch)
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)
    executor = CapabilityExecutor()
    entry = _direct_host_entry()

    response = executor._host_boundary_response_if_needed(
        entry=entry,
        principal_id="third_party_pack",
        request_id="run-1",
        start_time=time.time(),
    )
    assert response is not None
    phrase = response.output["confirmation_phrase"]
    approved = service.approve_request(
        response.output["request_id"],
        scope="once",
        config={"confirmation_text": phrase},
        ui_operator=_ui_operator(response.output["request_id"]),
    )
    assert approved["success"] is True

    followup = executor._host_boundary_response_if_needed(
        entry=entry,
        principal_id="third_party_pack",
        request_id="run-2",
        start_time=time.time(),
        request_context=_authority_context(
            "host.process.exec_guarded",
            response.output["request_id"],
            approved["token"],
        ),
    )

    assert followup is None


def test_unified_execute_direct_host_approved_retry_reaches_execution(tmp_path, monkeypatch):
    service = _authority_service(tmp_path, monkeypatch)
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)
    executor = _executor_for_direct_host_retry()
    entry = _direct_host_entry()

    first = executor._unified_execute(entry, "third_party_pack", {"args": {}, "request_id": "run-1"}, time.time())
    assert first.error_type == "critical_host_confirmation_required"
    approved = service.approve_request(
        first.output["request_id"],
        scope="once",
        config={"confirmation_text": first.output["confirmation_phrase"]},
        ui_operator=_ui_operator(first.output["request_id"]),
    )
    assert approved["success"] is True

    retry = executor._unified_execute(
        entry,
        "third_party_pack",
        {
            "args": {},
            "request_id": "run-2",
            "context": _authority_context("host.process.exec_guarded", first.output["request_id"], approved["token"]),
        },
        time.time(),
    )

    assert retry.success is True
    assert retry.output == {"executed": True}


def test_function_call_direct_host_approved_retry_reaches_execution(tmp_path, monkeypatch):
    service = _authority_service(tmp_path, monkeypatch)
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: service)
    executor = _executor_for_direct_host_retry()
    entry = _direct_host_entry()
    executor._function_registry = SimpleNamespace(
        get=lambda qualified_name: entry if qualified_name == entry.qualified_name else None,
        resolve_by_alias=lambda qualified_name: None,
    )

    first = executor._execute_function_call(
        "third_party_pack",
        {"qualified_name": entry.qualified_name, "args": {}, "request_id": "run-1"},
        time.time(),
    )
    assert first.error_type == "critical_host_confirmation_required"
    approved = service.approve_request(
        first.output["request_id"],
        scope="once",
        config={"confirmation_text": first.output["confirmation_phrase"]},
        ui_operator=_ui_operator(first.output["request_id"]),
    )
    assert approved["success"] is True

    retry = executor._execute_function_call(
        "third_party_pack",
        {
            "qualified_name": entry.qualified_name,
            "args": {},
            "request_id": "run-2",
            "context": _authority_context("host.process.exec_guarded", first.output["request_id"], approved["token"]),
        },
        time.time(),
    )

    assert retry.success is True
    assert retry.output == {"executed": True}


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
