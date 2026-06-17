from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_fallback_sorting_keeps_static_agent_company_status_before_generic_status():
    from ecosystem.defaultspack.transport.registry import (
        HttpRouteSpec,
        build_http_routes_from_specs,
    )

    class Server:
        def _invoke_fallback_block(self, block_module, request_data, path_params, inject=None):
            return {"block_module": block_module}

    routes = build_http_routes_from_specs(
        Server(),
        [
            HttpRouteSpec(
                "GET",
                "/api/agent/{id}/status",
                block_module="blocks.agent.status",
                path_inject={"id": "execution_id"},
            ),
            HttpRouteSpec(
                "GET",
                "/api/agent/company/status",
                block_module="ecosystem.rumi_operations_company_pack.blocks.agent.company.status",
            ),
        ],
    )
    patterns = [compiled.pattern for method, compiled, _, _, _ in routes if method == "GET"]

    assert patterns.index("^/api/agent/company/status$") < patterns.index(
        "^/api/agent/(?P<id>[^/]+)/status$"
    )


def test_chat_send_fallback_specs_target_chat_turn_flow():
    from ecosystem.defaultspack.transport.registry import _FALLBACK_HTTP_ROUTE_SPECS

    specs = {
        (spec.method, spec.pattern): spec
        for spec in _FALLBACK_HTTP_ROUTE_SPECS
    }

    completion = specs[("POST", "/v1/chat/completions")]
    message = specs[("POST", "/api/chat/conversations/{id}/messages")]
    assert completion.flow_id == "defaultspack.chat_turn"
    assert completion.fallback_block_module == "blocks.chat.send"
    assert completion.block_module == ""
    assert message.flow_id == "defaultspack.chat_turn"
    assert message.path_inject == {"id": "conversation_id"}
    stream = specs[("POST", "/api/chat/conversations/{id}/stream")]
    assert stream.flow_id == "defaultspack.chat_stream_turn"
    assert stream.fallback_block_module == "blocks.chat.stream"
    assert stream.path_inject == {"id": "conversation_id"}


def test_flow_yaml_routes_are_the_canonical_chat_ingress():
    from ecosystem.defaultspack.transport.registry import (
        canonical_http_route_specs,
        flow_http_route_specs,
    )

    flow_specs = {(spec.method, spec.pattern): spec for spec in flow_http_route_specs()}
    canonical = {(spec.method, spec.pattern): spec for spec in canonical_http_route_specs()}

    assert flow_specs[("POST", "/v1/chat/completions")].flow_id == "defaultspack.chat_turn"
    assert flow_specs[("POST", "/api/chat/conversations/{id}/messages")].flow_id == "defaultspack.chat_turn"
    assert flow_specs[("POST", "/api/chat/conversations/{id}/stream")].flow_id == "defaultspack.chat_stream_turn"
    assert canonical[("POST", "/api/chat/conversations/{id}/stream")].flow_id == "defaultspack.chat_stream_turn"


def test_template_function_routes_join_canonical_transport_registry():
    from ecosystem.defaultspack.transport.registry import (
        canonical_http_route_specs,
        template_http_route_specs,
    )

    template_routes = {(spec.method, spec.pattern): spec for spec in template_http_route_specs()}
    canonical = {(spec.method, spec.pattern): spec for spec in canonical_http_route_specs()}

    token_route = template_routes[("POST", "/api/context/token-estimate")]
    assert token_route.function_id == "context_token_estimate"
    assert token_route.function_name == "defaultspack:context_token_estimate"
    assert canonical[("POST", "/api/context/token-estimate")].function_name == (
        "defaultspack:context_token_estimate"
    )
    provider_key_route = canonical[("POST", "/api/ai/provider-key")]
    assert provider_key_route.function_name == "defaultspack:ai_set_provider_key"
    assert provider_key_route.sensitive is True
    external_template_route = canonical[("POST", "/api/external/templates")]
    assert external_template_route.function_name == "defaultspack:external_io_upsert_custom_template"
    assert external_template_route.sensitive is True


def test_pack_api_dispatches_defaultspack_interface_routes(monkeypatch):
    from core_runtime.pack_api_server import PackAPIHandler

    calls = []

    def ui_handler(request_data, context):
        calls.append((request_data, context))
        return {"status": "ok", "data": {"preview": request_data["conversation_id"]}}

    class Registry:
        def get(self, key, strategy="last"):
            if key == "io.http.route" and strategy == "all":
                return [
                    {
                        "method": "GET",
                        "pattern": "/api/ui/conversations/{id}/preview",
                        "handler": ui_handler,
                        "path_inject": {"id": "conversation_id"},
                    }
                ]
            return [] if strategy == "all" else None

    class Kernel:
        interface_registry = Registry()
        event_bus = None

    handler = object.__new__(PackAPIHandler)
    handler.path = "/api/ui/conversations/c1/preview?mode=short"
    handler.headers = {"Origin": "http://127.0.0.1:8765", "X-Test": "1"}
    captured = []
    handler._send_defaultspack_http_result = captured.append

    previous_kernel = PackAPIHandler.kernel
    monkeypatch.setattr(PackAPIHandler, "kernel", Kernel())
    try:
        assert handler._dispatch_defaultspack_http_route(
            "GET",
            "/api/ui/conversations/c1/preview",
        )
    finally:
        monkeypatch.setattr(PackAPIHandler, "kernel", previous_kernel)

    assert captured == [{"status": "ok", "data": {"preview": "c1"}}]
    request_data, context = calls[0]
    assert request_data["conversation_id"] == "c1"
    assert request_data["mode"] == "short"
    assert request_data["_method"] == "GET"
    assert context["owner_pack"] == "defaultspack"
    assert "_facade" in context


def test_pack_api_uses_direct_defaultspack_fallback_without_registered_routes(monkeypatch):
    from core_runtime.pack_api_server import PackAPIHandler
    import ecosystem.defaultspack.transport.http as transport_http

    calls = []

    def fake_invoke_block(module_name, input_data, context):
        calls.append((module_name, input_data, context))
        return {"status": "ok", "data": {"id": "c1", "model": input_data.get("model")}}

    class Registry:
        def get(self, key, strategy="last"):
            return [] if strategy == "all" else None

    class Kernel:
        interface_registry = Registry()
        event_bus = None

    monkeypatch.setattr(transport_http, "invoke_block", fake_invoke_block)

    handler = object.__new__(PackAPIHandler)
    handler.path = "/api/chat/conversations"
    handler.headers = {"Origin": "http://127.0.0.1:8765"}
    captured = []
    handler._send_defaultspack_http_result = captured.append

    previous_kernel = PackAPIHandler.kernel
    monkeypatch.setattr(PackAPIHandler, "kernel", Kernel())
    try:
        assert handler._dispatch_defaultspack_http_route(
            "POST",
            "/api/chat/conversations",
            {"model": "google/gemma-4-31b-it"},
        )
    finally:
        monkeypatch.setattr(PackAPIHandler, "kernel", previous_kernel)

    assert captured == [
        {"status": "ok", "data": {"id": "c1", "model": "google/gemma-4-31b-it"}}
    ]
    module_name, input_data, context = calls[0]
    assert module_name == "blocks.chat.create_conversation"
    assert input_data["model"] == "google/gemma-4-31b-it"
    assert context["owner_pack"] == "defaultspack"


def test_chat_send_route_handler_invokes_flow_route_before_block_fallback():
    from ecosystem.defaultspack.transport.registry import (
        HttpRouteSpec,
        build_http_routes_from_specs,
    )

    class Server:
        def __init__(self):
            self.calls = []

        def _invoke_flow_route(
            self,
            flow_id,
            request_data,
            path_params,
            inject=None,
            *,
            fallback_block_module="",
        ):
            self.calls.append(
                {
                    "flow_id": flow_id,
                    "request_data": request_data,
                    "path_params": path_params,
                    "inject": inject or {},
                    "fallback_block_module": fallback_block_module,
                }
            )
            return {"status": "ok"}

    server = Server()
    routes = build_http_routes_from_specs(
        server,
        [
            HttpRouteSpec(
                "POST",
                "/api/chat/conversations/{id}/messages",
                flow_id="defaultspack.chat_turn",
                fallback_block_module="blocks.chat.send",
                path_inject={"id": "conversation_id"},
            ),
        ],
    )
    method, compiled, handler, source, path_inject = routes[0]
    match = compiled.match("/api/chat/conversations/c1/messages")

    assert method == "POST"
    assert source == "fallback"
    assert path_inject == {"id": "conversation_id"}
    assert match is not None
    assert handler({"message": {"content": "hi"}}, match.groupdict()) == {"status": "ok"}
    assert server.calls == [
        {
            "flow_id": "defaultspack.chat_turn",
            "request_data": {"message": {"content": "hi"}, "_method": "POST"},
            "path_params": {"id": "c1"},
            "inject": {"id": "conversation_id"},
            "fallback_block_module": "blocks.chat.send",
        }
    ]


def test_http_flow_route_falls_back_to_legacy_chat_block():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer
    from ecosystem.defaultspack.domain.flow.result import FlowResult

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}
    calls = []

    def fake_fallback(module_name, request_data, path_params, inject=None):
        calls.append((module_name, request_data, path_params, inject or {}))
        return {"status": "ok", "data": {"legacy": True}}

    class FakeEngine:
        def execute(self, flow_id, trigger_input, context=None):
            return FlowResult(
                status="error",
                output={"status": "error", "error": {"code": "NOT_READY"}},
                metadata={"flow_id": flow_id},
            )

    server._invoke_fallback_block = fake_fallback
    import domain.flow as flow_module

    original = flow_module.FlowEngine
    flow_module.FlowEngine = FakeEngine
    try:
        result = server._invoke_flow_route(
            "defaultspack.chat_turn",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
            fallback_block_module="blocks.chat.send",
        )
    finally:
        flow_module.FlowEngine = original

    assert result == {"status": "ok", "data": {"legacy": True}}
    assert calls == [
        (
            "blocks.chat.send",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
        )
    ]


def test_authority_test_request_endpoint_is_disabled_by_default(monkeypatch):
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    monkeypatch.delenv("RUMI_AUTHORITY_TEST_ENDPOINT", raising=False)
    server = DefaultsHttpServer(facade=None)

    result = server._handle_authority_test_request({}, {})

    assert result["status"] == "error"
    assert result["error"]["code"] == "AUTHORITY_TEST_DISABLED"
    assert result["_http_status"] == 404


def test_authority_test_request_endpoint_creates_pending_decision(monkeypatch):
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    calls = []

    class Decision:
        request_id = "auth_smoke"

        def to_dict(self):
            return {
                "allowed": False,
                "approval_required": True,
                "request_id": self.request_id,
            }

    class Authority:
        def check(self, **kwargs):
            calls.append(kwargs)
            return Decision()

    monkeypatch.setenv("RUMI_AUTHORITY_TEST_ENDPOINT", "1")
    monkeypatch.setattr("core_runtime.authority.get_authority_service", lambda: Authority())
    server = DefaultsHttpServer(facade=None)

    result = server._handle_authority_test_request(
        {
            "provider_id": "anthropic",
            "api_id": "manual-smoke",
            "model_id": "claude-test",
            "conversation_id": "conv-1",
            "stream": False,
        },
        {},
    )

    assert result["status"] == "ok"
    assert result["data"]["approval_url"] == "/approval?request_id=auth_smoke"
    assert calls[0]["permission_id"] == "model.invoke"
    assert calls[0]["resource"] == {
        "kind": "model",
        "provider_id": "anthropic",
        "api_id": "manual-smoke",
        "model_id": "claude-test",
        "stream": False,
    }
    assert calls[0]["conversation_id"] == "conv-1"
    assert calls[0]["profile_id"] == "authority-test"
    assert calls[0]["node_id"] == "approval-window"


def test_authority_test_request_route_is_registered():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    server = DefaultsHttpServer(facade=None)
    handler, params, source, path_inject, _ = server._match_route(
        "POST",
        "/api/authority/test/request",
    )

    assert handler == server._handle_authority_test_request
    assert params == {}
    assert source == "fallback"
    assert path_inject == {}


def test_http_chat_flow_route_falls_back_when_success_output_is_not_chat_message():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer
    from ecosystem.defaultspack.domain.flow.result import FlowResult

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}
    calls = []

    def fake_fallback(module_name, request_data, path_params, inject=None):
        calls.append((module_name, request_data, path_params, inject or {}))
        return {"status": "ok", "data": {"id": "assistant-1", "role": "assistant"}}

    class FakeEngine:
        def execute(self, flow_id, trigger_input, context=None):
            return FlowResult(
                status="completed",
                output={"status": "ok", "data": {"outputs": {"ai_response": {"content": []}}}},
                metadata={"flow_id": flow_id},
            )

    server._invoke_fallback_block = fake_fallback
    import domain.flow as flow_module

    original = flow_module.FlowEngine
    flow_module.FlowEngine = FakeEngine
    try:
        result = server._invoke_flow_route(
            "defaultspack.chat_turn",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
            fallback_block_module="blocks.chat.send",
        )
    finally:
        flow_module.FlowEngine = original

    assert result == {"status": "ok", "data": {"id": "assistant-1", "role": "assistant"}}
    assert calls == [
        (
            "blocks.chat.send",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
        )
    ]


def test_http_chat_flow_route_returns_compatible_chat_message_output():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer
    from ecosystem.defaultspack.domain.flow.result import FlowResult

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    class FakeEngine:
        def execute(self, flow_id, trigger_input, context=None):
            return FlowResult(
                status="completed",
                output={
                    "status": "ok",
                    "data": {
                        "id": "assistant-1",
                        "role": "assistant",
                        "content": [{"type": "text", "text": "hi"}],
                    },
                },
                metadata={"flow_id": flow_id},
            )

    server._invoke_fallback_block = lambda *_args, **_kwargs: {"status": "error"}
    import domain.flow as flow_module

    original = flow_module.FlowEngine
    flow_module.FlowEngine = FakeEngine
    try:
        result = server._invoke_flow_route(
            "defaultspack.chat_turn",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
            fallback_block_module="blocks.chat.send",
        )
    finally:
        flow_module.FlowEngine = original

    assert result == {
        "status": "ok",
        "data": {
            "id": "assistant-1",
            "role": "assistant",
            "content": [{"type": "text", "text": "hi"}],
        },
    }


def test_http_chat_stream_flow_route_falls_back_when_output_is_not_sse():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer
    from ecosystem.defaultspack.domain.flow.result import FlowResult

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}
    calls = []

    def fake_fallback(module_name, request_data, path_params, inject=None):
        calls.append((module_name, request_data, path_params, inject or {}))
        return {"status": "ok", "data": {"_sse": True, "events": [{"type": "done"}]}}

    class FakeEngine:
        def execute(self, flow_id, trigger_input, context=None):
            return FlowResult(
                status="completed",
                output={"status": "ok", "data": {"outputs": {"stream_result": {}}}},
                metadata={"flow_id": flow_id},
            )

    server._invoke_fallback_block = fake_fallback
    import domain.flow as flow_module

    original = flow_module.FlowEngine
    flow_module.FlowEngine = FakeEngine
    try:
        result = server._invoke_flow_route(
            "defaultspack.chat_stream_turn",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
            fallback_block_module="blocks.chat.stream",
        )
    finally:
        flow_module.FlowEngine = original

    assert result == {"status": "ok", "data": {"_sse": True, "events": [{"type": "done"}]}}
    assert calls == [
        (
            "blocks.chat.stream",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
        )
    ]


def test_http_chat_stream_flow_route_falls_back_when_sse_events_are_stringified():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer
    from ecosystem.defaultspack.domain.flow.result import FlowResult

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}
    calls = []

    def fake_fallback(module_name, request_data, path_params, inject=None):
        calls.append((module_name, request_data, path_params, inject or {}))
        return {"_sse": True, "events": [{"type": "done"}]}

    class FakeEngine:
        def execute(self, flow_id, trigger_input, context=None):
            return FlowResult(
                status="completed",
                output={"status": "ok", "data": {"_sse": True, "events": "<generator object _engine_events>"}},
                metadata={"flow_id": flow_id},
            )

    server._invoke_fallback_block = fake_fallback
    import domain.flow as flow_module

    original = flow_module.FlowEngine
    flow_module.FlowEngine = FakeEngine
    try:
        result = server._invoke_flow_route(
            "defaultspack.chat_stream_turn",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
            fallback_block_module="blocks.chat.stream",
        )
    finally:
        flow_module.FlowEngine = original

    assert result == {"_sse": True, "events": [{"type": "done"}]}
    assert calls == [
        (
            "blocks.chat.stream",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
        )
    ]


def test_http_chat_stream_flow_route_returns_compatible_sse_output():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer
    from ecosystem.defaultspack.domain.flow.result import FlowResult

    server = DefaultsHttpServer.__new__(DefaultsHttpServer)
    server._build_context = lambda: {"request_id": "req-1"}

    class FakeEngine:
        def execute(self, flow_id, trigger_input, context=None):
            return FlowResult(
                status="completed",
                output={"status": "ok", "data": {"_sse": True, "events": [{"type": "done"}]}},
                metadata={"flow_id": flow_id},
            )

    server._invoke_fallback_block = lambda *_args, **_kwargs: {"status": "error"}
    import domain.flow as flow_module

    original = flow_module.FlowEngine
    flow_module.FlowEngine = FakeEngine
    try:
        result = server._invoke_flow_route(
            "defaultspack.chat_stream_turn",
            {"message": {"content": "hi"}},
            {"id": "c1"},
            {"id": "conversation_id"},
            fallback_block_module="blocks.chat.stream",
        )
    finally:
        flow_module.FlowEngine = original

    assert result == {"status": "ok", "data": {"_sse": True, "events": [{"type": "done"}]}}


def test_stdio_chat_message_uses_canonical_chat_turn_flow():
    from ecosystem.defaultspack.domain.flow.result import FlowResult
    from ecosystem.defaultspack.transport.stdio import DefaultsStdioTransport

    calls = []

    class FakeEngine:
        def execute(self, flow_id, trigger_input, context=None):
            calls.append((flow_id, trigger_input, context))
            return FlowResult(
                status="completed",
                output={
                    "status": "ok",
                    "data": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "hello"}],
                    },
                },
                metadata={"flow_id": flow_id},
            )

    import domain.flow as flow_module

    original = flow_module.FlowEngine
    flow_module.FlowEngine = FakeEngine
    try:
        result = DefaultsStdioTransport()._handle_request(
            {
                "method": "POST",
                "path": "/api/chat/conversations/c1/messages",
                "data": {"message": {"content": "hi"}},
            }
        )
    finally:
        flow_module.FlowEngine = original

    assert result == {
        "status": "ok",
        "data": {
            "role": "assistant",
            "content": [{"type": "text", "text": "hello"}],
        },
    }
    assert calls[0][0] == "defaultspack.chat_turn"
    assert calls[0][1]["conversation_id"] == "c1"


def test_cli_direct_send_message_uses_canonical_chat_turn_flow():
    from ecosystem.defaultspack.domain.flow.result import FlowResult
    from ecosystem.defaultspack.transport.cli import DirectBackend

    calls = []

    class FakeEngine:
        def execute(self, flow_id, trigger_input, context=None):
            calls.append((flow_id, trigger_input, context))
            return FlowResult(
                status="completed",
                output={
                    "status": "ok",
                    "data": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "hello"}],
                    },
                },
                metadata={"flow_id": flow_id},
            )

    import domain.flow as flow_module

    original = flow_module.FlowEngine
    flow_module.FlowEngine = FakeEngine
    try:
        result = DirectBackend().send_message(
            {"conversation_id": "c1", "message": {"content": "hi"}}
        )
    finally:
        flow_module.FlowEngine = original

    assert result == {
        "status": "ok",
        "data": {
            "role": "assistant",
            "content": [{"type": "text", "text": "hello"}],
        },
    }
    assert calls[0][0] == "defaultspack.chat_turn"
    assert calls[0][1]["conversation_id"] == "c1"


def test_registry_sorting_keeps_static_agent_company_status_before_generic_status():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    def generic_status(request_data, context):
        return {"handler": "generic", "request_data": request_data}

    def company_status(request_data, context):
        return {"handler": "company", "request_data": request_data}

    class Facade:
        def get_interface(self, key, strategy=None):
            if key != "io.http.route":
                return None
            return [
                {
                    "method": "GET",
                    "pattern": "/api/agent/{id}/status",
                    "handler": generic_status,
                    "path_inject": {"id": "execution_id"},
                },
                {
                    "method": "GET",
                    "pattern": "/api/agent/company/status",
                    "handler": company_status,
                    "path_inject": {},
                },
            ]

    server = DefaultsHttpServer(Facade())
    handler, params, source, path_inject, _ = server._match_route("GET", "/api/agent/company/status")

    assert handler is company_status
    assert params == {}
    assert source == "registry"
    assert path_inject == {}


def test_registry_chat_send_route_is_adapted_to_chat_turn_flow():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    def hardcoded_chat_send(request_data, context):
        return {"handler": "legacy", "request_data": request_data}

    class Facade:
        def get_interface(self, key, strategy=None):
            if key != "io.http.route":
                return None
            return [
                {
                    "method": "POST",
                    "pattern": "/api/chat/conversations/{id}/messages",
                    "handler": hardcoded_chat_send,
                    "path_inject": {"id": "conversation_id"},
                },
            ]

    server = DefaultsHttpServer(Facade())
    calls = []

    def fake_flow_route(
        flow_id,
        request_data,
        path_params,
        inject=None,
        *,
        fallback_block_module="",
    ):
        calls.append((flow_id, request_data, path_params, inject or {}, fallback_block_module))
        return {"status": "ok", "data": {"flow": True}}

    server._invoke_flow_route = fake_flow_route
    handler, params, source, path_inject, _ = server._match_route(
        "POST",
        "/api/chat/conversations/c1/messages",
    )

    assert source == "registry"
    assert path_inject == {"id": "conversation_id"}
    assert getattr(handler, "_defaultspack_flow_route_handler", False) is True
    assert handler({"message": {"content": "hi"}}, params) == {
        "status": "ok",
        "data": {"flow": True},
    }
    assert calls == [
        (
            "defaultspack.chat_turn",
            {"message": {"content": "hi"}, "_method": "POST"},
            {"id": "c1"},
            {"id": "conversation_id"},
            "blocks.chat.send",
        )
    ]


def test_registry_chat_flow_handler_keeps_path_params_through_http_dispatch_shape():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    def hardcoded_chat_send(request_data, context):
        return {"handler": "legacy", "request_data": request_data}

    class Facade:
        def get_interface(self, key, strategy=None):
            if key != "io.http.route":
                return None
            return [
                {
                    "method": "POST",
                    "pattern": "/api/chat/conversations/{id}/messages",
                    "handler": hardcoded_chat_send,
                    "path_inject": {"id": "conversation_id"},
                },
            ]

    server = DefaultsHttpServer(Facade())
    calls = []

    def fake_flow_route(
        flow_id,
        request_data,
        path_params,
        inject=None,
        *,
        fallback_block_module="",
    ):
        calls.append((flow_id, request_data, path_params, inject or {}, fallback_block_module))
        return {"status": "ok", "data": {"flow": True}}

    server._invoke_flow_route = fake_flow_route
    handler, params, source, path_inject, _ = server._match_route(
        "POST",
        "/api/chat/conversations/c1/messages",
    )
    request_data = {"message": {"content": "hi"}}
    for url_param, data_key in path_inject.items():
        request_data[data_key] = params.get(url_param, "")
    request_data["_method"] = "POST"
    request_data["_actual_method"] = "POST"

    if getattr(handler, "_defaultspack_flow_route_handler", False):
        result = handler(request_data, params)
    else:
        context = server._build_context()
        context["_facade"] = server.facade
        result = handler(request_data, context)

    assert source == "registry"
    assert result == {"status": "ok", "data": {"flow": True}}
    assert calls[-1][2] == {"id": "c1"}
    assert calls[-1][1]["conversation_id"] == "c1"


def test_registry_chat_stream_route_is_adapted_to_chat_stream_turn_flow():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    def hardcoded_chat_stream(request_data, context):
        return {"handler": "legacy", "request_data": request_data}

    class Facade:
        def get_interface(self, key, strategy=None):
            if key != "io.http.route":
                return None
            return [
                {
                    "method": "POST",
                    "pattern": "/api/chat/conversations/{id}/stream",
                    "handler": hardcoded_chat_stream,
                    "path_inject": {"id": "conversation_id"},
                },
            ]

    server = DefaultsHttpServer(Facade())
    calls = []

    def fake_flow_route(
        flow_id,
        request_data,
        path_params,
        inject=None,
        *,
        fallback_block_module="",
    ):
        calls.append((flow_id, request_data, path_params, inject or {}, fallback_block_module))
        return {"status": "ok", "data": {"_sse": True, "events": [{"type": "done"}]}}

    server._invoke_flow_route = fake_flow_route
    handler, params, source, path_inject, _ = server._match_route(
        "POST",
        "/api/chat/conversations/c1/stream",
    )

    assert source == "registry"
    assert path_inject == {"id": "conversation_id"}
    assert handler({"message": {"content": "hi"}}, params) == {
        "status": "ok",
        "data": {"_sse": True, "events": [{"type": "done"}]},
    }
    assert calls == [
        (
            "defaultspack.chat_stream_turn",
            {"message": {"content": "hi"}, "_method": "POST"},
            {"id": "c1"},
            {"id": "conversation_id"},
            "blocks.chat.stream",
        )
    ]


@pytest.mark.parametrize(
    ("method", "path", "block_module", "path_params", "inject", "payload"),
    [
        (
            "GET",
            "/api/agent/companies/acme/status",
            "blocks.company.status",
            {"company_id": "acme"},
            {"company_id": "company_id"},
            {"_method": "GET"},
        ),
        (
            "PUT",
            "/api/agent/companies/acme/agents/bot",
            "blocks.company.agents",
            {"company_id": "acme", "agent_id": "bot"},
            {"company_id": "company_id", "agent_id": "agent_id"},
            {"_method": "PUT", "action": "update"},
        ),
        (
            "POST",
            "/api/integrations/p2p/events",
            "blocks.integrations.p2p",
            {},
            {},
            {"_method": "POST"},
        ),
        (
            "POST",
            "/api/p2p/messages/send",
            "blocks.p2p.messages_send",
            {},
            {},
            {"_method": "POST"},
        ),
        (
            "DELETE",
            "/api/p2p/peers/peer-a",
            "blocks.p2p.peers",
            {"peer_id": "peer-a"},
            {"peer_id": "peer_id"},
            {"_method": "DELETE"},
        ),
        (
            "POST",
            "/api/chat/conversations/c1/compact",
            "blocks.chat.compact",
            {"id": "c1"},
            {"id": "conversation_id"},
            {"_method": "POST"},
        ),
        (
            "GET",
            "/api/coding/workspaces/ws1",
            "blocks.coding.workspace.get",
            {"workspace_id": "ws1"},
            {"workspace_id": "workspace_id"},
            {"_method": "GET"},
        ),
        (
            "POST",
            "/api/coding/workspaces/ws1/trust",
            "blocks.coding.workspace.trust",
            {"workspace_id": "ws1"},
            {"workspace_id": "workspace_id"},
            {"_method": "POST"},
        ),
    ],
)
def test_new_fallback_routes_dispatch_to_expected_blocks(
    method,
    path,
    block_module,
    path_params,
    inject,
    payload,
):
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    server = DefaultsHttpServer(facade=None)
    calls = []

    def fake_invoke(module_name, request_data, params, route_inject=None):
        calls.append(
            {
                "block_module": module_name,
                "request_data": request_data,
                "path_params": params,
                "inject": route_inject or {},
            }
        )
        return {"status": "ok"}

    server._invoke_fallback_block = fake_invoke
    handler, params, source, path_inject, _ = server._match_route(method, path)

    assert handler is not None
    assert source == "fallback"
    assert params == path_params
    assert path_inject == inject
    assert handler({"body": "kept"}, params) == {"status": "ok"}
    assert calls[-1]["block_module"] == block_module
    assert calls[-1]["path_params"] == path_params
    assert calls[-1]["inject"] == inject
    for key, value in payload.items():
        assert calls[-1]["request_data"][key] == value


def test_fallback_specs_list_company_p2p_compact_and_workspace_routes():
    from ecosystem.defaultspack.transport.registry import _FALLBACK_HTTP_ROUTE_SPECS

    routes = {(spec.method, spec.pattern, spec.block_module) for spec in _FALLBACK_HTTP_ROUTE_SPECS}
    expected = {
        ("GET", "/api/agent/companies", "blocks.company.list"),
        ("POST", "/api/agent/companies", "blocks.company.create"),
        ("GET", "/api/company", "blocks.company.list"),
        ("POST", "/api/company/bootstrap", "blocks.company.bootstrap"),
        ("GET", "/api/agent/companies/{company_id}/status", "blocks.company.status"),
        ("PUT", "/api/agent/companies/{company_id}/agents/{agent_id}", "blocks.company.agents"),
        ("POST", "/api/agent/companies/{company_id}/channels/{channel_id}/messages", "blocks.company.messages"),
        ("GET", "/api/agent/companies/{company_id}/threads", "blocks.company.threads"),
        ("POST", "/api/agent/companies/{company_id}/threads/{thread_id}/messages", "blocks.company.messages"),
        ("PUT", "/api/agent/companies/{company_id}/tasks/{task_id}", "blocks.company.tasks"),
        ("POST", "/api/agent/companies/{company_id}/tasks/{task_id}/dispatch", "blocks.company.dispatch"),
        ("GET", "/api/agent/companies/{company_id}/runs", "blocks.company.runs"),
        ("GET", "/api/agent/companies/{company_id}/agents/{agent_id}/inbox", "blocks.company.inbox"),
        ("POST", "/api/agent/companies/{company_id}/supervisor/tick", "blocks.company.supervisor_tick"),
        ("GET", "/api/agent/companies/{company_id}/summaries", "blocks.company.summary"),
        ("DELETE", "/api/agent/companies/{company_id}/inbound-routes/{route_id}", "blocks.company.inbound_routes"),
        ("GET", "/api/p2p/status", "blocks.p2p.status"),
        ("POST", "/api/p2p/identity/rotate", "blocks.p2p.identity"),
        ("PUT", "/api/p2p/peers/{peer_id}", "blocks.p2p.peers"),
        ("POST", "/api/p2p/messages/inbound", "blocks.p2p.messages_inbound"),
        ("POST", "/api/integrations/p2p/events", "blocks.integrations.p2p"),
        ("POST", "/api/chat/conversations/{id}/compact", "blocks.chat.compact"),
        ("POST", "/api/chat/conversations/{id}/auto-compact", "blocks.chat.auto_compact"),
        ("GET", "/api/coding/workspaces/get", "blocks.coding.workspace.get"),
        ("POST", "/api/coding/workspaces/select", "blocks.coding.workspace.select"),
        ("GET", "/api/coding/workspaces/{workspace_id}", "blocks.coding.workspace.get"),
        ("POST", "/api/coding/workspaces/{workspace_id}/trust", "blocks.coding.workspace.trust"),
    }

    assert expected <= routes


def test_p2p_pre_auth_only_exposes_signed_integration_event():
    manifest = json.loads((DEFAULTSPACK_ROOT / "ecosystem.json").read_text(encoding="utf-8"))
    pre_auth_routes = manifest["pre_auth_routes"]
    method_paths = {
        (route.get("method"), route.get("path"))
        for route in pre_auth_routes
        if route.get("path")
    }

    assert ("POST", "/api/integrations/p2p/events") in method_paths
    assert not any(
        str(route.get("path") or route.get("path_prefix") or "").startswith("/api/p2p")
        for route in pre_auth_routes
    )


def test_routes_json_documents_new_route_groups():
    routes = json.loads((DEFAULTSPACK_ROOT / "routes.json").read_text(encoding="utf-8"))["routes"]
    method_paths = {(route["method"], route["path"]) for route in routes}
    expected = {
        ("POST", "/api/chat/conversations/{id}/compact"),
        ("GET", "/api/agent/companies/{company_id}/status"),
        ("POST", "/api/agent/companies/{company_id}/dispatch"),
        ("POST", "/api/agent/companies/{company_id}/supervisor/tick"),
        ("GET", "/api/agent/companies/{company_id}/summaries"),
        ("GET", "/api/agent/companies/{company_id}/runs"),
        ("POST", "/api/agent/companies/{company_id}/tasks/{task_id}/dispatch"),
        ("POST", "/api/agent/companies/{company_id}/inbound-routes/{route_id}/ingest"),
        ("GET", "/api/p2p/status"),
        ("POST", "/api/p2p/pairing/start"),
        ("POST", "/api/integrations/p2p/events"),
        ("GET", "/api/coding/workspaces/{workspace_id}"),
        ("POST", "/api/coding/workspaces/{workspace_id}/select"),
    }

    assert expected <= method_paths
