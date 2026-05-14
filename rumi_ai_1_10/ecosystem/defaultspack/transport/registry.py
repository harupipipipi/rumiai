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
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/stop", block_module="blocks.chat.stop", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/export", block_module="blocks.chat.export_conversation", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("GET", "/api/chat/channels", block_module="blocks.chat.channel.list"),
    HttpRouteSpec("POST", "/api/chat/channels", block_module="blocks.chat.channel.create"),
    HttpRouteSpec("GET", "/api/chat/channels/{id}", block_module="blocks.chat.channel.get", path_inject={"id": "id"}),
    HttpRouteSpec("POST", "/api/chat/channels/{id}/join", block_module="blocks.chat.channel.join", path_inject={"id": "id"}),
    HttpRouteSpec("POST", "/api/chat/channels/{id}/leave", block_module="blocks.chat.channel.leave", path_inject={"id": "id"}),
    HttpRouteSpec("POST", "/api/chat/channels/{id}/messages", block_module="blocks.chat.channel.send_message", path_inject={"id": "id"}),
    HttpRouteSpec("GET", "/api/chat/channels/{id}/messages", block_module="blocks.chat.channel.get_messages", path_inject={"id": "id"}),
    HttpRouteSpec("POST", "/api/chat/channels/{id}/messages/{msg_id}/reply", block_module="blocks.chat.channel.reply", path_inject={"id": "id", "msg_id": "msg_id"}),
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/summarize", block_module="blocks.chat.summarize_and_trim", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/auto-trim", block_module="blocks.chat.auto_trim", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("GET", "/api/chat/conversations/{id}/run-results/{run_id}/browser-screenshots", block_module="blocks.chat.browser_screenshots", path_inject={"id": "conversation_id", "run_id": "run_id"}),
    HttpRouteSpec("GET", "/v1/conversations/{id}/run-results/{run_id}/browser-screenshots", block_module="blocks.chat.browser_screenshots", path_inject={"id": "conversation_id", "run_id": "run_id"}),
    HttpRouteSpec("GET", "/api/chat/conversations/{id}/artifact-file", block_module="blocks.chat.artifact_file", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("GET", "/api/integrations/secrets", block_module="blocks.integrations.secrets"),
    HttpRouteSpec("POST", "/api/integrations/secrets", block_module="blocks.integrations.secrets"),
    HttpRouteSpec("POST", "/api/integrations/slack/events", block_module="blocks.integrations.slack"),
    HttpRouteSpec("POST", "/api/integrations/line/webhook", block_module="blocks.integrations.line"),
    HttpRouteSpec("POST", "/api/integrations/discord/interactions", block_module="blocks.integrations.discord"),
    HttpRouteSpec("POST", "/api/integrations/discord/events", block_module="blocks.integrations.discord"),
    HttpRouteSpec("GET", "/api/external/tokens", block_module="blocks.external.tokens"),
    HttpRouteSpec("POST", "/api/external/tokens", block_module="blocks.external.tokens"),
    HttpRouteSpec("GET", "/api/external/sources", block_module="blocks.external.sources"),
    HttpRouteSpec("POST", "/api/external/sources", block_module="blocks.external.sources"),
    HttpRouteSpec("GET", "/api/external/templates", block_module="blocks.external.templates"),
    HttpRouteSpec("POST", "/api/external/templates", block_module="blocks.external.templates"),
    HttpRouteSpec("POST", "/api/webhooks/inbound/{webhook_id}", block_module="blocks.webhooks.inbound", path_inject={"webhook_id": "webhook_id"}),
    HttpRouteSpec("GET", "/api/webhooks/endpoints", block_module="blocks.webhooks.endpoints"),
    HttpRouteSpec("POST", "/api/webhooks/endpoints", block_module="blocks.webhooks.endpoints"),
    HttpRouteSpec("PUT", "/api/webhooks/endpoints/{webhook_id}", block_module="blocks.webhooks.endpoints", path_inject={"webhook_id": "webhook_id"}),
    HttpRouteSpec("DELETE", "/api/webhooks/endpoints/{webhook_id}", block_module="blocks.webhooks.endpoints", path_inject={"webhook_id": "webhook_id"}),
    HttpRouteSpec("POST", "/api/webhooks/endpoints/{webhook_id}/test", block_module="blocks.webhooks.inbound", path_inject={"webhook_id": "webhook_id"}),
    HttpRouteSpec("GET", "/api/webhooks/public-urls", block_module="blocks.webhooks.public_url"),
    HttpRouteSpec("POST", "/api/webhooks/public-urls", block_module="blocks.webhooks.public_url"),
    HttpRouteSpec("DELETE", "/api/webhooks/public-urls/{url_id}", block_module="blocks.webhooks.public_url", path_inject={"url_id": "url_id"}),
    HttpRouteSpec("POST", "/api/agent/execute", block_module="blocks.agent.execute"),
    HttpRouteSpec("POST", "/api/agent/{id}/approve", block_module="blocks.agent.approve", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/agent/{id}/reject", block_module="blocks.agent.reject", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/agent/{id}/cancel", block_module="blocks.agent.cancel", path_inject={"id": "execution_id"}),
    HttpRouteSpec("GET", "/api/agent/company/manifest", block_module="ecosystem.rumi_operations_company_pack.blocks.agent.company.manifest"),
    HttpRouteSpec("GET", "/api/agent/company/status", block_module="ecosystem.rumi_operations_company_pack.blocks.agent.company.status"),
    HttpRouteSpec("POST", "/api/agent/company/bootstrap", block_module="ecosystem.rumi_operations_company_pack.blocks.agent.company.bootstrap"),
    HttpRouteSpec("GET", "/api/agent/{id}/status", block_module="blocks.agent.status", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/agent/multi/execute", block_module="blocks.agent.multi_execute"),
    HttpRouteSpec("GET", "/api/agent/multi/{id}/status", block_module="blocks.agent.multi_status", path_inject={"id": "session_id"}),
    HttpRouteSpec("POST", "/api/agent/multi/{id}/message", block_module="blocks.agent.multi_message", path_inject={"id": "session_id"}),
    HttpRouteSpec("POST", "/api/agent/{id}/instruct", block_module="blocks.agent.add_instruction", path_inject={"id": "execution_id"}),
    HttpRouteSpec("GET", "/api/agent/schedules", block_module="blocks.agent.scheduler.list"),
    HttpRouteSpec("POST", "/api/agent/schedules", block_module="blocks.agent.scheduler.create"),
    HttpRouteSpec("GET", "/api/agent/schedules/{id}", block_module="blocks.agent.scheduler.get", path_inject={"id": "schedule_id"}),
    HttpRouteSpec("PUT", "/api/agent/schedules/{id}", block_module="blocks.agent.scheduler.update", path_inject={"id": "schedule_id"}),
    HttpRouteSpec("DELETE", "/api/agent/schedules/{id}", block_module="blocks.agent.scheduler.delete", path_inject={"id": "schedule_id"}),
    HttpRouteSpec("POST", "/api/agent/schedules/{id}/trigger", block_module="blocks.agent.scheduler.trigger", path_inject={"id": "schedule_id"}),
    HttpRouteSpec("POST", "/api/agent/schedules/{id}/pause", block_module="blocks.agent.scheduler.pause", path_inject={"id": "schedule_id"}),
    HttpRouteSpec("POST", "/api/agent/schedules/{id}/resume", block_module="blocks.agent.scheduler.resume", path_inject={"id": "schedule_id"}),
    HttpRouteSpec("GET", "/api/agent/schedules/{id}/history", block_module="blocks.agent.scheduler.history", path_inject={"id": "schedule_id"}),
    HttpRouteSpec("GET", "/api/agent/org", block_module="blocks.agent.org.list"),
    HttpRouteSpec("POST", "/api/agent/org", block_module="blocks.agent.org.create"),
    HttpRouteSpec("GET", "/api/agent/org/roles", block_module="blocks.agent.org.list_roles"),
    HttpRouteSpec("POST", "/api/agent/org/roles", block_module="blocks.agent.org.define_role"),
    HttpRouteSpec("GET", "/api/agent/org/{id}", block_module="blocks.agent.org.get", path_inject={"id": "id"}),
    HttpRouteSpec("DELETE", "/api/agent/org/{id}", block_module="blocks.agent.org.delete", path_inject={"id": "id"}),
    HttpRouteSpec("POST", "/api/agent/org/{id}/members", block_module="blocks.agent.org.add_member", path_inject={"id": "id"}),
    HttpRouteSpec("DELETE", "/api/agent/org/{id}/members/{agent_id}", block_module="blocks.agent.org.remove_member", path_inject={"id": "id", "agent_id": "agent_id"}),
    HttpRouteSpec("POST", "/api/agent/org/{id}/ask", block_module="blocks.agent.org.ask", path_inject={"id": "id"}),
    HttpRouteSpec("POST", "/api/agent/org/{id}/instruct", block_module="blocks.agent.org.instruct", path_inject={"id": "id"}),
    HttpRouteSpec("POST", "/api/agent/org/{id}/report", block_module="blocks.agent.org.report", path_inject={"id": "id"}),
    HttpRouteSpec("POST", "/api/agent/org/{id}/transfer", block_module="blocks.agent.org.transfer_context", path_inject={"id": "id"}),
    HttpRouteSpec("GET", "/api/capabilities", block_module="blocks.capability.list"),
    HttpRouteSpec("GET", "/api/capabilities/{id}", block_module="blocks.capability.manifest", path_inject={"id": "capability_id"}),
    HttpRouteSpec("GET", "/api/coding/context", block_module="blocks.coding.context"),
    HttpRouteSpec("POST", "/api/coding/files/read", block_module="blocks.coding.file_read"),
    HttpRouteSpec("POST", "/api/coding/files/write", block_module="blocks.coding.file_write"),
    HttpRouteSpec("POST", "/api/coding/files/create", block_module="blocks.coding.file_create"),
    HttpRouteSpec("POST", "/api/coding/files/delete", block_module="blocks.coding.file_delete"),
    HttpRouteSpec("GET", "/api/coding/files", block_module="blocks.coding.file_list"),
    HttpRouteSpec("POST", "/api/coding/files/search", block_module="blocks.coding.file_search"),
    HttpRouteSpec("POST", "/api/coding/terminal/exec", block_module="blocks.coding.terminal_exec"),
    HttpRouteSpec("POST", "/api/coding/terminal/stream", block_module="blocks.coding.terminal_stream"),
    HttpRouteSpec("GET", "/api/coding/git/status", block_module="blocks.coding.git_status"),
    HttpRouteSpec("GET", "/api/coding/git/diff", block_module="blocks.coding.git_diff"),
    HttpRouteSpec("GET", "/api/coding/git/branch", block_module="blocks.coding.git_branch"),
    HttpRouteSpec("POST", "/api/coding/git/branch", block_module="blocks.coding.git_branch"),
    HttpRouteSpec("POST", "/api/coding/git/commit", block_module="blocks.coding.git_commit"),
    HttpRouteSpec("POST", "/api/coding/approvals/approve", block_module="blocks.coding.approval_approve"),
    HttpRouteSpec("POST", "/api/coding/approvals/deny", block_module="blocks.coding.approval_deny"),
    HttpRouteSpec("POST", "/api/research/local-search", block_module="blocks.research.local_search"),
    HttpRouteSpec("POST", "/api/research/web-search", block_module="blocks.research.web_search"),
    HttpRouteSpec("POST", "/api/research/reddit-search", block_module="blocks.research.reddit_search"),
    HttpRouteSpec("POST", "/api/research/report", block_module="blocks.research.report"),
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
    HttpRouteSpec("GET", "/api/tools", block_module="blocks.tool.list"),
    HttpRouteSpec("POST", "/api/tools/invoke", block_module="blocks.tool.invoke"),
    HttpRouteSpec("POST", "/api/tools/browser-computer", block_module="blocks.tool.browser_computer"),
    HttpRouteSpec("POST", "/api/tools/browser-companion/bridge/poll", block_module="blocks.tool.browser_companion_bridge_poll"),
    HttpRouteSpec("POST", "/api/tools/browser-companion/bridge/result", block_module="blocks.tool.browser_companion_bridge_result"),
    HttpRouteSpec("POST", "/api/tools/create", block_module="blocks.tool.create"),
    HttpRouteSpec("PUT", "/api/tools/{name}", block_module="blocks.tool.update", path_inject={"name": "name"}),
    HttpRouteSpec("DELETE", "/api/tools/{name}", block_module="blocks.tool.delete", path_inject={"name": "name"}),
    HttpRouteSpec("GET", "/api/tools/{name}/export", block_module="blocks.tool.export", path_inject={"name": "name"}),
    HttpRouteSpec("GET", "/api/agent-service/manifest", block_module="blocks.capability.manifest"),
    HttpRouteSpec("POST", "/api/coding/files/diff", block_module="blocks.coding.file_diff"),
    HttpRouteSpec("POST", "/api/coding/files/patch", block_module="blocks.coding.file_patch"),
    HttpRouteSpec("POST", "/api/coding/files/snapshot", block_module="blocks.coding.file_snapshot"),
    HttpRouteSpec("POST", "/api/coding/files/restore", block_module="blocks.coding.file_restore"),
    HttpRouteSpec("POST", "/api/coding/git/diff", block_module="blocks.coding.git_diff"),
    HttpRouteSpec("POST", "/api/coding/git/push", block_module="blocks.coding.git_push"),
    HttpRouteSpec("POST", "/api/context/compact", block_module="blocks.context.compact"),
    HttpRouteSpec("POST", "/api/context/restore", block_module="blocks.context.restore"),
    HttpRouteSpec("GET", "/api/artifacts", block_module="blocks.artifact.list"),
    HttpRouteSpec("POST", "/api/artifacts", block_module="blocks.artifact.create"),
    HttpRouteSpec("GET", "/api/artifacts/{id}", block_module="blocks.artifact.get", path_inject={"id": "artifact_id"}),
    HttpRouteSpec("GET", "/api/share", block_module="blocks.share.list"),
    HttpRouteSpec("POST", "/api/share", block_module="blocks.share.create"),
    HttpRouteSpec("GET", "/api/share/{token}", block_module="blocks.share.get", path_inject={"token": "token"}),
    HttpRouteSpec("DELETE", "/api/share/{token}", block_module="blocks.share.revoke", path_inject={"token": "token"}),
    HttpRouteSpec("GET", "/api/dev/inspect", block_module="blocks.dev.inspect"),
    HttpRouteSpec("GET", "/api/dev/prompt-history", block_module="blocks.dev.prompt_history"),
    HttpRouteSpec("POST", "/api/dev/edit-prompt", block_module="blocks.dev.edit_prompt_live"),
    HttpRouteSpec("POST", "/api/dev/replay", block_module="blocks.dev.replay"),
    HttpRouteSpec("GET", "/api/ai/provider-key", block_module="blocks.ai.provider_key"),
    HttpRouteSpec("POST", "/api/ai/provider-key", block_module="blocks.ai.provider_key"),
    HttpRouteSpec("GET", "/api/ai/catalog", block_module="blocks.ai.catalog"),
    HttpRouteSpec("GET", "/api/ai/providers", block_module="blocks.ai.providers"),
    HttpRouteSpec("GET", "/api/ai/models", block_module="blocks.ai.models"),
    HttpRouteSpec("GET", "/api/ai/profiles", block_module="blocks.ai.profiles"),
    HttpRouteSpec("GET", "/api/ui/catalog", block_module="blocks.ui.catalog"),
    HttpRouteSpec("GET", "/api/ui/settings", block_module="blocks.ui.settings"),
    HttpRouteSpec("PUT", "/api/ui/settings", block_module="blocks.ui.settings"),
    HttpRouteSpec("GET", "/api/ui/commands", block_module="blocks.ui.commands"),
    HttpRouteSpec("POST", "/api/ui/commands/execute", block_module="blocks.ui.commands"),
    HttpRouteSpec("POST", "/api/ui/clipboard", block_module="blocks.ui.clipboard"),
    HttpRouteSpec("GET", "/api/ui/conversations/{id}/preview", block_module="blocks.ui.conversation_preview", path_inject={"id": "conversation_id"}),
]

_ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS = [
    HttpRouteSpec("GET", "/api/health", handler_name="_handle_health"),
    HttpRouteSpec("GET", "/api/context", handler_name="_handle_context_info"),
    HttpRouteSpec("GET", "/", handler_name="_handle_chat_redirect"),
    HttpRouteSpec("GET", "/chat", handler_name="_handle_static"),
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
