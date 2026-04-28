from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ecosystem.defaultspack.domain.extensions.runtime import get_extension_registry


@dataclass(frozen=True)
class HttpRouteSpec:
    method: str
    pattern: str
    block_module: str = ""
    handler_name: str = ""
    path_inject: Dict[str, str] = field(default_factory=dict)


_FALLBACK_HTTP_ROUTE_SPECS = [
    HttpRouteSpec("POST", "/v1/chat/completions", block_module="blocks.chat.send"),
    HttpRouteSpec("POST", "/api/chat/conversations", block_module="blocks.chat.create_conversation"),
    HttpRouteSpec("GET", "/api/chat/conversations", block_module="blocks.chat.list_conversations"),
    HttpRouteSpec("GET", "/api/chat/conversations/{id}", block_module="blocks.chat.get_conversation", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("PUT", "/api/chat/conversations/{id}", block_module="blocks.chat.update_conversation", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("DELETE", "/api/chat/conversations/{id}", block_module="blocks.chat.delete_conversation", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/messages", block_module="blocks.chat.send", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/stream", block_module="blocks.chat.stream", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/export", block_module="blocks.chat.export_conversation", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/summarize", block_module="blocks.chat.summarize_and_trim", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/auto-trim", block_module="blocks.chat.auto_trim", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/agent/execute", block_module="blocks.agent.execute"),
    HttpRouteSpec("POST", "/api/agent/{id}/approve", block_module="blocks.agent.approve", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/agent/{id}/reject", block_module="blocks.agent.reject", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/agent/{id}/cancel", block_module="blocks.agent.cancel", path_inject={"id": "execution_id"}),
    HttpRouteSpec("GET", "/api/agent/{id}/status", block_module="blocks.agent.status", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/agent/multi/execute", block_module="blocks.agent.multi_execute"),
    HttpRouteSpec("GET", "/api/agent/multi/{id}/status", block_module="blocks.agent.multi_status", path_inject={"id": "session_id"}),
    HttpRouteSpec("POST", "/api/agent/multi/{id}/message", block_module="blocks.agent.multi_message", path_inject={"id": "session_id"}),
    HttpRouteSpec("POST", "/api/agent/{id}/instruct", block_module="blocks.agent.add_instruction", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/consent/check", block_module="blocks.tool.consent_check"),
    HttpRouteSpec("POST", "/api/consent/{id}/confirm", block_module="blocks.tool.consent_confirm", path_inject={"id": "consent_id"}),
    HttpRouteSpec("POST", "/api/packs/defaultspack/knowledge", block_module="blocks.knowledge.create"),
    HttpRouteSpec("GET", "/api/packs/defaultspack/knowledge", block_module="blocks.knowledge.list"),
    HttpRouteSpec("POST", "/api/packs/defaultspack/knowledge/search", block_module="blocks.knowledge.search"),
    HttpRouteSpec("GET", "/api/packs/defaultspack/knowledge/{id}", block_module="blocks.knowledge.get", path_inject={"id": "id"}),
    HttpRouteSpec("PUT", "/api/packs/defaultspack/knowledge/{id}", block_module="blocks.knowledge.update", path_inject={"id": "id"}),
    HttpRouteSpec("DELETE", "/api/packs/defaultspack/knowledge/{id}", block_module="blocks.knowledge.delete", path_inject={"id": "id"}),
    HttpRouteSpec("PUT", "/api/prompts/{name}", block_module="blocks.prompt.update", path_inject={"name": "name"}),
    HttpRouteSpec("DELETE", "/api/prompts/{name}", block_module="blocks.prompt.delete", path_inject={"name": "name"}),
    HttpRouteSpec("POST", "/api/prompts/convert", block_module="blocks.prompt.convert"),
    HttpRouteSpec("POST", "/api/tools/create", block_module="blocks.tool.create"),
    HttpRouteSpec("PUT", "/api/tools/{name}", block_module="blocks.tool.update", path_inject={"name": "name"}),
    HttpRouteSpec("DELETE", "/api/tools/{name}", block_module="blocks.tool.delete", path_inject={"name": "name"}),
    HttpRouteSpec("GET", "/api/tools/{name}/export", block_module="blocks.tool.export", path_inject={"name": "name"}),
    HttpRouteSpec("GET", "/api/dev/inspect", block_module="blocks.dev.inspect"),
    HttpRouteSpec("GET", "/api/dev/prompt-history", block_module="blocks.dev.prompt_history"),
    HttpRouteSpec("POST", "/api/dev/edit-prompt", block_module="blocks.dev.edit_prompt_live"),
    HttpRouteSpec("POST", "/api/dev/replay", block_module="blocks.dev.replay"),
    HttpRouteSpec("GET", "/api/ai/provider-key", block_module="blocks.ai.provider_key"),
    HttpRouteSpec("POST", "/api/ai/provider-key", block_module="blocks.ai.provider_key"),
    HttpRouteSpec("GET", "/api/ui/catalog", block_module="blocks.ui.catalog"),
    HttpRouteSpec("GET", "/api/ui/settings", block_module="blocks.ui.settings"),
    HttpRouteSpec("PUT", "/api/ui/settings", block_module="blocks.ui.settings"),
    HttpRouteSpec("GET", "/api/ui/conversations/{id}/preview", block_module="blocks.ui.conversation_preview", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("GET", "/api/health", handler_name="_handle_health"),
    HttpRouteSpec("GET", "/api/context", handler_name="_handle_context_info"),
    HttpRouteSpec("GET", "/", handler_name="_handle_static"),
    HttpRouteSpec("GET", "/static/{path}", handler_name="_handle_static_file"),
]

_ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS = [
    HttpRouteSpec("GET", "/api/health", handler_name="_handle_health"),
    HttpRouteSpec("GET", "/api/context", handler_name="_handle_context_info"),
    HttpRouteSpec("GET", "/", handler_name="_handle_static"),
    HttpRouteSpec("GET", "/static/{path}", handler_name="_handle_static_file"),
]


class TransportRegistry:
    """Transport extension lookup for route/entrypoint migration."""

    def __init__(self) -> None:
        self._registry = get_extension_registry().transports()

    def list_transports(self) -> List[Dict[str, Any]]:
        return self._registry.list(enabled_only=True)

    def get_transport(self, transport_id: str) -> Optional[Dict[str, Any]]:
        return self._registry.get(transport_id)


def build_http_routes_from_specs(server: Any, specs: List[HttpRouteSpec]):
    routes = []
    for spec in specs:
        regex_pattern = re.sub(
            r"\{(\w+)\}",
            lambda match: r"(?P<{}>.+)".format(match.group(1))
            if match.group(1) == "path"
            else r"(?P<{}>[^/]+)".format(match.group(1)),
            spec.pattern,
        )
        compiled = re.compile("^" + regex_pattern + "$")
        if spec.block_module:
            def _handler(
                request_data,
                path_params,
                *,
                block_module=spec.block_module,
                path_inject=dict(spec.path_inject),
                route_method=spec.method,
            ):
                payload = dict(request_data or {})
                payload.setdefault("_method", route_method)
                return server._invoke_fallback_block(
                    block_module,
                    payload,
                    path_params,
                    path_inject,
                )
            handler = _handler
        else:
            handler = getattr(server, spec.handler_name)
        routes.append((spec.method, compiled, handler, "fallback", dict(spec.path_inject)))
    return routes


def build_always_available_http_routes(server: Any):
    return build_http_routes_from_specs(server, _ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS)


def build_fallback_http_routes(server: Any):
    fallback_specs = [
        spec
        for spec in _FALLBACK_HTTP_ROUTE_SPECS
        if spec.pattern not in {item.pattern for item in _ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS}
    ]
    return build_http_routes_from_specs(
        server,
        fallback_specs + _ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS,
    )
