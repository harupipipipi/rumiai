from __future__ import annotations

import json
import sys
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _exact_target_window(**overrides):
    target = {
        "app": "ChatGPT Atlas",
        "pid": 321,
        "window_id": 654,
        "x": 10,
        "y": 20,
        "width": 1200,
        "height": 800,
    }
    target.update(overrides)
    return target


def test_viewer_broker_client_reads_env_url_and_token(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_URL", "http://127.0.0.1:8770")
    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_TOKEN", "secret-token")

    client = ViewerBrokerClient.from_environment()

    assert client.available() is True
    assert client.url == "http://127.0.0.1:8770"
    assert client.token == "secret-token"


def test_viewer_broker_client_reads_connection_json(tmp_path, monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    connection = tmp_path / "host_broker" / "connection.json"
    connection.parent.mkdir(parents=True, exist_ok=True)
    connection.write_text(
        json.dumps(
            {
                "version": 1,
                "host": "127.0.0.1",
                "port": 8771,
                "url": "http://127.0.0.1:8771",
                "token": "file-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RUMI_VIEWER_HOST_BROKER_URL", raising=False)
    monkeypatch.delenv("RUMI_VIEWER_HOST_BROKER_TOKEN", raising=False)
    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_CONNECTION", str(connection))

    client = ViewerBrokerClient.from_environment()

    assert client.available() is True
    assert client.url == "http://127.0.0.1:8771"
    assert client.token == "file-token"


def test_viewer_broker_client_fails_closed_on_configured_port_mismatch(tmp_path, monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    connection = tmp_path / "connection.json"
    connection.write_text(
        json.dumps(
            {
                "version": 1,
                "host": "127.0.0.1",
                "port": 8770,
                "url": "http://127.0.0.1:8770",
                "token": "wrong-broker-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RUMI_VIEWER_HOST_BROKER_URL", raising=False)
    monkeypatch.delenv("RUMI_VIEWER_HOST_BROKER_TOKEN", raising=False)
    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_CONNECTION", str(connection))
    monkeypatch.setenv("RUMI_VIEWER_BROKER_PORT", "8771")

    client = ViewerBrokerClient.from_environment()

    assert client.available() is False


def test_viewer_broker_client_rejects_invalid_port_and_non_loopback_url(tmp_path, monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_URL", "http://192.0.2.1:8771")
    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_TOKEN", "token")
    monkeypatch.setenv("RUMI_VIEWER_BROKER_PORT", "not-a-port")
    assert ViewerBrokerClient.from_environment().available() is False

    monkeypatch.setenv("RUMI_VIEWER_BROKER_PORT", "8771")
    assert ViewerBrokerClient.from_environment().available() is False


def test_viewer_broker_client_does_not_fallback_when_explicit_url_pair_is_incomplete(
    tmp_path, monkeypatch
):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    connection = tmp_path / "connection.json"
    connection.write_text(
        json.dumps(
            {
                "version": 1,
                "host": "127.0.0.1",
                "port": 8770,
                "url": "http://127.0.0.1:8770",
                "token": "file-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_URL", "http://127.0.0.1:8771")
    monkeypatch.delenv("RUMI_VIEWER_HOST_BROKER_TOKEN", raising=False)
    monkeypatch.setenv("RUMI_VIEWER_HOST_BROKER_CONNECTION", str(connection))

    assert ViewerBrokerClient.from_environment().available() is False


def test_viewer_broker_client_waits_longer_than_helper_timeout(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import viewer_broker_client
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(viewer_broker_client.urllib.request, "urlopen", fake_urlopen)

    ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token").permissions()

    assert seen["timeout"] == viewer_broker_client.VIEWER_BROKER_REQUEST_TIMEOUT_SECONDS
    assert seen["timeout"] > viewer_broker_client.VIEWER_BROKER_HELPER_TIMEOUT_SECONDS


def test_viewer_broker_client_execute_intent_posts_payload(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    captured: dict[str, object] = {}

    def fake_request(self, method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"ok": True, "intent_id": "intent_1"}

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")

    result = client.execute_intent({"intent": "open", "target": "settings"})

    assert result == {"ok": True, "intent_id": "intent_1"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/host/intent/execute"
    assert captured["payload"] == {"intent": "open", "target": "settings"}


def test_viewer_broker_client_start_stream_posts_payload(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    captured: dict[str, object] = {}

    def fake_request(self, method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"ok": True, "stream_id": "stream_1"}

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")

    result = client.start_stream({"topic": "desktop"})

    assert result == {"ok": True, "stream_id": "stream_1"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/host/stream/start"
    assert captured["payload"] == {"topic": "desktop"}


def test_viewer_broker_client_stop_stream_posts_payload_with_stream_id(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    captured: dict[str, object] = {}

    def fake_request(self, method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")
    payload = {"reason": "done"}

    result = client.stop_stream("stream 1/2", payload)

    assert result == {"ok": True}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/host/stream/stop"
    assert captured["payload"] == {"reason": "done", "stream_id": "stream 1/2"}
    assert payload == {"reason": "done"}


def test_viewer_broker_client_stream_events_gets_encoded_stream_id(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    captured: dict[str, object] = {}

    def fake_request(self, method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"ok": True, "events": []}

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")

    result = client.stream_events("stream 1/2")

    assert result == {"ok": True, "events": []}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/host/stream/events/stream%201%2F2"
    assert captured["payload"] is None


def test_viewer_broker_client_drops_haze_sequence_from_helper_approval_args(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    captured: dict[str, object] = {}

    def fake_request(self, method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"ok": True, "result": {"action": "computer.show_app"}}

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")

    client.run_computer(
        "computer.show_app",
        {
            "action": "computer.show_app",
            "payload": {"app": "Vivaldi", "computer_use_haze_sequence_id": "run_1"},
            "approval_token": "tok",
            "computer_use_haze_sequence_id": "run_1",
        },
        context={"conversation_id": "conv_1"},
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/host/computer/run"
    assert captured["payload"]["args"] == {"app": "Vivaldi"}
    assert captured["payload"]["approval_token"] == "tok"


def test_computer_router_routes_darwin_computer_calls_to_viewer(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            return {"action": function_id, "routed": True, "payload": dict(args), "context": dict(context or {})}

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "approval_token": "tok", "window": _exact_target_window()},
        {"conversation_id": "conv_1"},
    )

    assert result["routed"] is True
    assert result["action"] == "computer.click"
    assert result["context"]["conversation_id"] == "conv_1"


def test_computer_router_routes_windows_computer_calls_to_viewer_without_local_fallback(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            return {"action": function_id, "routed": True, "payload": dict(args)}

    def fail_if_local_controller_runs(*args, **kwargs):
        raise AssertionError("Windows computer actions must not fall back to the local controller")

    monkeypatch.delenv("RUMI_COMPUTER_HOST_INTERNAL", raising=False)
    monkeypatch.setattr(computer_router.platform, "system", lambda: "Windows")
    monkeypatch.setattr(computer_router, "_run_local_controller", fail_if_local_controller_runs)
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "approval_token": "tok", "window": _exact_target_window()},
        {"conversation_id": "conv_1"},
    )

    assert result == {
        "action": "computer.click",
        "routed": True,
        "payload": {"x": 10, "approval_token": "tok", "window": _exact_target_window()},
    }


def test_computer_router_materializes_persisted_target_into_viewer_approval(monkeypatch):
    from domain.safety import approval
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    approval.reset_approval_state_for_tests()
    selected_target = _exact_target_window(title="Draft")
    captured = {}

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            captured["args"] = dict(args)
            return {"action": function_id, "requires_approval": True}

    monkeypatch.delenv("RUMI_COMPUTER_HOST_INTERNAL", raising=False)
    monkeypatch.setattr(computer_router.platform, "system", lambda: "Windows")
    monkeypatch.setattr(computer_router, "_persisted_target_window", lambda **kwargs: selected_target)
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.type",
        {"app": "Atlas", "text": "hello"},
        {"conversation_id": "conv_1"},
        tool_name="computer_use",
    )

    materialized_window = _exact_target_window()
    assert captured["args"] == {
        "app": "Atlas",
        "text": "hello",
        "window": materialized_window,
    }
    request = approval.get_approval_request(result["approval_request_id"])
    assert request["details"]["arguments"] == {
        "action": "computer.type",
        "payload": captured["args"],
    }


def test_computer_router_materializes_each_target_sensitive_action_class(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    selected_target = _exact_target_window()
    captured = []

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            captured.append((function_id, dict(args)))
            return {"action": function_id, "routed": True}

    monkeypatch.delenv("RUMI_COMPUTER_HOST_INTERNAL", raising=False)
    monkeypatch.setattr(computer_router.platform, "system", lambda: "Windows")
    monkeypatch.setattr(computer_router, "_persisted_target_window", lambda **kwargs: selected_target)
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    actions = (
        ("computer.type", {"text": "hello"}),
        ("computer.key", {"key": "Enter"}),
        ("computer.scroll", {"amount": 1}),
        ("computer.click_text", {"text": "Save"}),
        ("computer.semantic_action", {"intent": "Save"}),
        ("computer.pid_event", {"pid": 321, "sub_action": "click"}),
        ("computer.move", {"x": 10, "y": 20}),
        ("computer.click", {"x": 10, "y": 20}),
        ("computer.drag", {"x1": 10, "y1": 20, "x2": 30, "y2": 40}),
        ("computer.screenshot", {"target": "selected_window"}),
        ("computer.ocr", {"target": "selected_window"}),
        ("computer.ax_tree", {"target": "selected_window"}),
    )
    for action, payload in actions:
        result = computer_router.run_computer_action(action, payload, {})
        assert result["routed"] is True

    assert [action for action, _payload in captured] == [action for action, _payload in actions]
    assert all(payload["window"] == selected_target for _action, payload in captured)


def test_computer_router_requires_exact_selection_before_broker_or_approval(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, *args, **kwargs):
            raise AssertionError("targetless action must not reach the Viewer broker")

    monkeypatch.delenv("RUMI_COMPUTER_HOST_INTERNAL", raising=False)
    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router, "_persisted_target_window", lambda **kwargs: None)
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))
    monkeypatch.setattr(
        computer_router,
        "_approval_module",
        lambda: (_ for _ in ()).throw(AssertionError("targetless action must not create an approval")),
    )

    for action, payload, yolo_mode in (
        ("computer.semantic_action", {"intent": "Save"}, True),
        ("computer.screenshot", {}, False),
    ):
        result = computer_router.run_computer_action(action, payload, {}, yolo_mode=yolo_mode)

        assert result["is_error"] is True
        assert result["error_code"] == "EXACT_TARGET_SELECTION_REQUIRED"
        assert result["recovery"]["recommended_next_actions"] == ["computer.select_window"]
        assert "requires_approval" not in result


def test_computer_router_rejects_non_alias_app_filter_for_persisted_target(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, *args, **kwargs):
            raise AssertionError("mismatched target filter must not reach the Viewer broker")

    monkeypatch.delenv("RUMI_COMPUTER_HOST_INTERNAL", raising=False)
    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        computer_router,
        "_persisted_target_window",
        lambda **kwargs: _exact_target_window(app="ChatGPT Atlas"),
    )
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.type",
        {"app": "ChatGPT", "text": "hello"},
        {},
    )

    assert result["is_error"] is True
    assert result["error_code"] == "EXACT_TARGET_SELECTION_REQUIRED"


def test_computer_router_rejects_approval_when_persisted_selection_changes(monkeypatch):
    from domain.safety import approval
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    approval.reset_approval_state_for_tests()
    selected_target = {"value": _exact_target_window(app="ChatGPT Atlas")}
    broker_args = []

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            received = dict(args)
            broker_args.append(received)
            token = str(received.pop("approval_token", ""))
            if not token:
                return {"action": function_id, "requires_approval": True}
            verification = approval.verify_execution_token(
                token,
                function_id,
                approval.hash_arguments({"action": function_id, "payload": received}),
                pack_id="defaultspack",
                conversation_id="conv_1",
            )
            if not verification.valid:
                return {
                    "action": function_id,
                    "is_error": True,
                    "error_code": "APPROVAL_TOKEN_TARGET_MISMATCH",
                }
            return {"action": function_id, "executed": True}

    monkeypatch.delenv("RUMI_COMPUTER_HOST_INTERNAL", raising=False)
    monkeypatch.setattr(computer_router.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        computer_router,
        "_persisted_target_window",
        lambda **kwargs: dict(selected_target["value"]),
    )
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    pending = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "y": 20},
        {"conversation_id": "conv_1"},
        tool_name="computer_use",
    )
    token = approval.approve(pending["approval_request_id"])["token"]
    selected_target["value"] = _exact_target_window(app="Other App", pid=999, window_id=777)

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "y": 20, "approval_token": token},
        {"conversation_id": "conv_1"},
        tool_name="computer_use",
    )

    assert broker_args[0]["window"] == _exact_target_window()
    assert broker_args[1]["window"] == _exact_target_window(app="Other App", pid=999, window_id=777)
    assert result["is_error"] is True
    assert result["error_code"] == "APPROVAL_TOKEN_TARGET_MISMATCH"


def test_computer_router_uses_context_token_for_viewer_approval(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            return {"action": function_id, "approval_token_seen": args.get("approval_token")}

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "window": _exact_target_window()},
        {"tool_approval_tokens": {"computer.click": "tok_ctx"}},
        tool_name="computer_use",
    )

    assert result["approval_token_seen"] == "tok_ctx"


def test_computer_router_adds_text_input_guidance_to_viewer_observations(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            return {"action": function_id, "ok": True, "recommended_next_actions": ["custom.next"]}

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    for action in ("computer.screenshot", "computer.observe"):
        payload = {"target": "display"} if action == "computer.screenshot" else {}
        result = computer_router.run_computer_action(
            action,
            payload,
            {"conversation_id": "conv_1"},
            tool_name="browser_computer",
        )

        assert result["action"] == action
        assert result["recommended_next_actions"][0] == "custom.next"
        assert "computer.type" in result["recommended_next_actions"]
        assert "computer.key" in result["recommended_next_actions"]
        assert "normal approval gates still apply" in result["input_guidance"]


def test_computer_router_does_not_add_text_guidance_to_viewer_approval_result(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            return {
                "action": function_id,
                "requires_approval": True,
                "approval_request_id": "apr_viewer",
                "recommended_next_actions": ["approve_request"],
            }

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.screenshot",
        {"target": "display"},
        {"conversation_id": "conv_1"},
    )

    assert result["requires_approval"] is True
    assert result["recommended_next_actions"] == ["approve_request"]
    assert "input_guidance" not in result


def test_computer_router_skips_viewer_for_internal_host_execution(tmp_path, monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    captured: dict[str, object] = {}

    def fake_run(self, action, payload, *, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = dict(payload)
        captured["yolo_mode"] = yolo_mode
        return {"action": action, "local": True}

    monkeypatch.setenv("RUMI_COMPUTER_HOST_INTERNAL", "1")
    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(BrowserComputerController, "run", fake_run)

    result = computer_router.run_computer_action(
        "computer.type",
        {"text": "hello"},
        {"conversation_id": "conv_1"},
        artifact_root=tmp_path,
        yolo_mode=True,
    )

    assert result["local"] is True
    assert captured["action"] == "computer.type"
    assert captured["payload"] == {"text": "hello"}
    assert captured["yolo_mode"] is True


def test_computer_router_returns_recovery_when_viewer_is_unavailable(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return False

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action("computer.screenshot", {"target": "display"}, {})

    assert result["is_error"] is True
    assert result["permission_subject"] == "Rumi Viewer"
    assert "Open Rumi Viewer" in result["recovery"]["note"]


def test_computer_router_fails_closed_when_windows_viewer_is_unavailable(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class UnavailableClient:
        def available(self):
            return False

    def fail_if_local_controller_runs(*args, **kwargs):
        raise AssertionError("Windows computer actions must not fall back to the local controller")

    monkeypatch.delenv("RUMI_COMPUTER_HOST_INTERNAL", raising=False)
    monkeypatch.setattr(computer_router.platform, "system", lambda: "Windows")
    monkeypatch.setattr(computer_router, "_run_local_controller", fail_if_local_controller_runs)
    monkeypatch.setattr(
        computer_router.ViewerBrokerClient,
        "from_environment",
        classmethod(lambda cls: UnavailableClient()),
    )

    result = computer_router.run_computer_action("computer.screenshot", {"target": "display"}, {})

    assert result["is_error"] is True
    assert result["recovery"]["kind"] == "viewer_connection_required"
    assert result["recovery"]["requires_viewer_connection"] is True
    assert result["permission_subject"] == "Rumi Viewer"


def test_computer_router_returns_recovery_when_viewer_connection_is_stale(monkeypatch, tmp_path):
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.screenshot",
        {"target": "display"},
        {},
        artifact_root=tmp_path,
    )

    assert result["is_error"] is True
    assert "unavailable" in result["reason"]
    assert result["permission_subject"] == "Rumi Viewer"


def test_viewer_broker_client_includes_artifact_root_but_not_pack_chat_store(tmp_path, monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    captured: dict[str, object] = {}
    chat_store_path = tmp_path / "chat" / "conversations.json"

    def fake_request(self, method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = dict(payload or {})
        return {"ok": True, "result": {"action": "computer.screenshot"}}

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(chat_store_path))
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")

    client.run_computer(
        "computer.screenshot",
        {},
        context={"conversation_id": "conv_1", "pack_id": "pack_1"},
        artifact_root=tmp_path,
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/host/computer/run"
    assert captured["payload"]["artifact_root"] == str(tmp_path)
    assert "chat_store_path" not in captured["payload"]
    assert captured["payload"]["pack_id"] == "pack_1"


def test_viewer_broker_client_unwraps_controller_shaped_approval_args(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    captured: dict[str, object] = {}

    def fake_request(self, method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = dict(payload or {})
        return {"ok": True, "result": {"action": "computer.windows"}}

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")

    client.run_computer(
        "computer.windows",
        {
            "action": "computer.windows",
            "payload": {},
            "approval_token": "approval-token",
        },
        context={"conversation_id": "conv_1", "pack_id": "pack_1"},
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/host/computer/run"
    assert captured["payload"]["approval_token"] == "approval-token"
    assert captured["payload"]["args"] == {}
    assert captured["payload"]["conversation_id"] == "conv_1"


def test_viewer_broker_client_preserves_approval_payload_from_broker(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    def fake_request(self, method, path, payload=None):
        return {
            "ok": False,
            "audit_id": "host-audit-1",
            "result": {
                "action": "computer.click",
                "requires_approval": True,
                "approval_token": "tok",
            },
            "error": {"code": "APPROVAL_REQUIRED", "message": "Approval required."},
        }

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    client = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret-token")

    result = client.run_computer("computer.click", {"x": 10})

    assert result["requires_approval"] is True
    assert result["approval_token"] == "tok"
    assert result["error_code"] == "APPROVAL_REQUIRED"
    assert result["host_audit_id"] == "host-audit-1"


def test_viewer_broker_client_preserves_only_safe_type_failure_diagnostics(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    def fake_request(self, method, path, payload=None):
        return {
            "ok": False,
            "audit_id": "host-audit-type",
            "diagnostics": {
                "error_code": "TYPE_VERIFICATION_UNAVAILABLE",
                "input_dispatched": False,
                "dispatched_units": 0,
                "failure_stage": "initial_target_verification",
                "text": "private",
                "approval_token": "token",
                "pid": 123,
                "window_title": "private",
                "nested": {"raw_args": "private"},
            },
            "error": {"code": "TYPE_COMPLETION_NOT_VERIFIED", "message": "Typing failed."},
        }

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    result = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret").run_computer(
        "computer.type", {"text": "private"}
    )

    assert result["diagnostics"] == {
        "error_code": "TYPE_VERIFICATION_UNAVAILABLE",
        "input_dispatched": False,
        "dispatched_units": 0,
        "failure_stage": "initial_target_verification",
    }


def test_viewer_broker_client_preserves_only_safe_posted_delivery_facts(monkeypatch):
    from ecosystem.defaultspack.domain.host_bridge.viewer_broker_client import ViewerBrokerClient

    def fake_request(self, method, path, payload=None):
        return {
            "ok": False,
            "audit_id": "host-audit-posted",
            "result": {
                "action": "computer.type",
                "executed": True,
                "delivered": True,
                "background": True,
                "foreground": False,
                "driver": "mac_accessibility",
                "can_parallel_user_work": True,
                "requires_foreground": False,
                "uses_physical_input": False,
                "completion_verified": False,
                "outcome": "posted_unverified",
                "verification_required": "screenshot",
                "ax_candidate": {
                    "driver_registered": True,
                    "driver_available": True,
                    "background_type_capable": True,
                    "pyobjc_ax_import_available": False,
                    "ax_process_trusted": False,
                    "ax_set_value_unsafe_app": False,
                    "target_app_present": True,
                    "target_bundle_present": True,
                    "target_pid_present": True,
                    "target_window_present": True,
                    "attempted": False,
                    "result_code": "AX_IMPORT_UNAVAILABLE",
                    "raw_target": "private AX target",
                },
                "text": "private text",
                "url": "https://example.invalid/?secret=query",
                "window_title": "private title",
                "pid": 123,
                "window_id": 456,
                "approval_token": "private token",
                "raw_error": "private error",
            },
            "error": {"code": "TYPE_COMPLETION_NOT_VERIFIED", "message": "private raw broker error"},
        }

    monkeypatch.setattr(ViewerBrokerClient, "_request", fake_request)
    result = ViewerBrokerClient(url="http://127.0.0.1:8770", token="secret").run_computer(
        "computer.type", {"text": "private request", "approval_token": "approval"}
    )

    assert result["executed"] is True
    assert result["delivered"] is True
    assert result["background"] is True
    assert result["driver"] == "mac_accessibility"
    assert result["completion_verified"] is False
    assert result["outcome"] == "posted_unverified"
    assert result["verification_required"] == "screenshot"
    assert result["ax_candidate"]["result_code"] == "AX_IMPORT_UNAVAILABLE"
    assert result["ax_candidate"]["pyobjc_ax_import_available"] is False
    assert "raw_target" not in result["ax_candidate"]
    serialized = str(result)
    for private in (
        "private text",
        "secret=query",
        "private title",
        "123",
        "456",
        "private token",
        "private error",
        "private request",
        "private raw broker error",
        "private AX target",
    ):
        assert private not in serialized


def test_computer_router_wraps_viewer_approval_into_request_id(monkeypatch):
    from domain.safety import approval
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    approval.reset_approval_state_for_tests()

    class FakeClient:
        def available(self):
            return True

        def run_computer(self, function_id, args, context=None, artifact_root=None):
            return {
                "action": function_id,
                "requires_approval": True,
                "approval_token": "viewer_tok",
                "approval_hint": "approval required",
            }

    monkeypatch.setattr(computer_router.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(computer_router.ViewerBrokerClient, "from_environment", classmethod(lambda cls: FakeClient()))

    result = computer_router.run_computer_action(
        "computer.click",
        {"x": 10, "y": 20, "window": _exact_target_window()},
        {"conversation_id": "conv_1", "owner_pack": "pack_1"},
        tool_name="computer_use",
    )

    assert result["requires_approval"] is True
    assert result["approval_required"] is True
    assert result["tool_name"] == "computer_use"
    assert result["operation"] == "computer.click"
    assert result["payload"] == {"x": 10, "y": 20, "window": _exact_target_window()}
    assert str(result["approval_request_id"]).startswith("apr_")
    assert result["message"] == "approval required"
    assert result["user_prompt"] == "承認してください"

    decision = approval.approve(result["approval_request_id"])
    encoded = decision["token"].split(".", 1)[0]
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8"))
    assert payload["operation"] == "computer.click"
    assert payload["function_id"] == "computer.click"
    assert payload["pack_id"] == "pack_1"
    assert payload["conversation_id"] == "conv_1"


def test_tool_executor_routes_local_computer_tools_through_router(monkeypatch):
    from domain.tool.executor import ToolExecutor
    from ecosystem.defaultspack.domain.host_bridge import computer_router

    captured: dict[str, object] = {}

    def fake_router(action, payload, context=None, *, tool_name="computer_use", artifact_root=None, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = dict(payload)
        captured["context"] = dict(context or {})
        captured["tool_name"] = tool_name
        return {"action": action, "ok": True}

    monkeypatch.setattr(computer_router, "run_computer_action", fake_router)

    result = ToolExecutor()._execute_local(
        "computer_use",
        {"action": "click", "x": 10, "y": 20},
        {"conversation_id": "conv_1"},
    )

    assert result["is_error"] is False
    assert captured["action"] == "computer.click"
    assert captured["payload"]["x"] == 10
    assert captured["payload"]["y"] == 20
    assert captured["tool_name"] == "computer_use"
    assert captured["context"]["conversation_id"] == "conv_1"


def test_computer_host_helper_accepts_workspace_artifact_root(monkeypatch, tmp_path):
    from core_runtime.host_broker import computer_host_helper

    chat_store_path = tmp_path / "chat" / "conversations.json"
    artifact_root = chat_store_path.parent / "conversations" / "conv-1" / "workspace" / "tools" / "computer"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(chat_store_path))

    result = computer_host_helper._validated_artifact_root(str(artifact_root))

    assert result == artifact_root.resolve()


def test_computer_host_helper_rejects_non_workspace_artifact_root(tmp_path):
    from core_runtime.host_broker import computer_host_helper

    invalid_root = tmp_path / "rogue" / "computer"

    try:
        computer_host_helper._validated_artifact_root(str(invalid_root))
    except ValueError as exc:
        assert "artifact_root" in str(exc)
    else:  # pragma: no cover - safety net for explicit failure messaging
        raise AssertionError("expected artifact_root validation to fail")


def test_defaultspack_browser_computer_block_uses_router(monkeypatch):
    import ecosystem.defaultspack.blocks.tool.browser_computer as browser_computer_block

    captured: dict[str, object] = {}

    def fake_router(action, payload, context=None, *, tool_name="computer_use", artifact_root=None, yolo_mode=False):
        captured["action"] = action
        captured["payload"] = dict(payload)
        captured["context"] = dict(context or {})
        captured["tool_name"] = tool_name
        captured["artifact_root"] = artifact_root
        captured["yolo_mode"] = yolo_mode
        return {"action": action, "ok": True}

    monkeypatch.setattr(browser_computer_block, "run_computer_action", fake_router)

    result = browser_computer_block.run(
        {"action": "computer.observe", "payload": {"detail": "full"}},
        {"conversation_workspace_dir": "/tmp/work", "yolo_mode": "true"},
    )

    assert result["status"] == "ok"
    assert captured["action"] == "computer.observe"
    assert captured["payload"]["detail"] == "full"
    assert captured["context"]["conversation_workspace_dir"] == "/tmp/work"
    assert captured["tool_name"] == "browser_computer"
    assert captured["yolo_mode"] is True
