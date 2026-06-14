from __future__ import annotations

from functools import lru_cache
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ecosystem.defaultspack.domain.components import get_domain_component_registry
from ecosystem.defaultspack.domain.extensions.runtime import get_extension_registry
from ecosystem.defaultspack.domain.tool.security import is_trusted_pack_id


@dataclass(frozen=True)
class HttpRouteSpec:
    method: str
    pattern: str
    function_id: str = ""
    legacy_block_module: str = ""
    flow_id: str = ""
    handler_name: str = ""
    path_inject: Dict[str, str] = field(default_factory=dict)
    defaults: Dict[str, Any] = field(default_factory=dict)
    pre_auth: bool = False
    sensitive: bool = False
    block_module: str = ""
    function_name: str = ""
    fallback_block_module: str = ""

    def __post_init__(self) -> None:
        resolved_function_id = str(self.function_id or self.function_name or "").strip()
        resolved_legacy_block = str(
            self.legacy_block_module or self.fallback_block_module or ""
        ).strip()
        if self.block_module and not resolved_function_id:
            try:
                from domain.function_runtime.registry import function_id_for_block_module

                resolved_function_id = str(
                    function_id_for_block_module(self.block_module) or ""
                ).strip()
            except Exception:
                resolved_function_id = ""
        if self.block_module and not resolved_legacy_block:
            resolved_legacy_block = str(self.block_module).strip()
        if resolved_function_id and not self.function_name:
            object.__setattr__(self, "function_name", resolved_function_id)
        if resolved_legacy_block and not self.fallback_block_module:
            object.__setattr__(self, "fallback_block_module", resolved_legacy_block)
        object.__setattr__(self, "function_id", resolved_function_id)
        object.__setattr__(self, "legacy_block_module", resolved_legacy_block)


_ROUTE_PARAM_RE = re.compile(r"\{(\w+)\}")


_ALLOWED_FIRST_PARTY_COMPONENT_ROUTE_BLOCK_MODULES = {
    "blocks.integrations.discord",
    "blocks.integrations.line",
    "blocks.integrations.slack",
    "blocks.ui.catalog",
}


def _pack_approved_for_component_routes(pack_id: str) -> bool:
    pack_id = str(pack_id or "").strip()
    if not pack_id:
        return False
    if is_trusted_pack_id(pack_id):
        return True
    try:
        from core_runtime.approval_manager import get_approval_manager

        approved, _reason = get_approval_manager().is_pack_approved_and_verified(pack_id)
        return bool(approved)
    except Exception:
        return False


def _safe_component_route_block_module(module_name: str, source_pack_id: str) -> bool:
    module_name = str(module_name or "").strip()
    if not module_name:
        return True
    return (
        is_trusted_pack_id(source_pack_id)
        and module_name in _ALLOWED_FIRST_PARTY_COMPONENT_ROUTE_BLOCK_MODULES
    )


def _component_route_target_allowed(
    *,
    source_pack_id: str,
    block_module: str = "",
    fallback_block_module: str = "",
    handler_name: str = "",
) -> bool:
    if not _pack_approved_for_component_routes(source_pack_id):
        return False
    if block_module and not _safe_component_route_block_module(block_module, source_pack_id):
        return False
    if fallback_block_module and not _safe_component_route_block_module(
        fallback_block_module,
        source_pack_id,
    ):
        return False
    if handler_name and not is_trusted_pack_id(source_pack_id):
        return False
    return True


def http_route_sort_key(method: str, pattern: str, index: int = 0):
    """Sort exact/static routes before parameterized catch-all siblings."""
    segments = [segment for segment in str(pattern or "").split("/") if segment]
    param_count = 0
    catch_all_count = 0
    static_segment_count = 0
    for segment in segments:
        match = _ROUTE_PARAM_RE.fullmatch(segment)
        if match is None:
            static_segment_count += 1
            continue
        param_count += 1
        if match.group(1) == "path":
            catch_all_count += 1
    literal_chars = len(_ROUTE_PARAM_RE.sub("", str(pattern or "")))
    return (
        str(method or "").upper(),
        catch_all_count,
        param_count,
        -static_segment_count,
        -len(segments),
        -literal_chars,
        index,
    )


def compile_http_route_pattern(pattern: str):
    regex_pattern = _ROUTE_PARAM_RE.sub(
        lambda match: r"(?P<{}>.+)".format(match.group(1))
        if match.group(1) == "path"
        else r"(?P<{}>[^/]+)".format(match.group(1)),
        pattern,
    )
    return re.compile("^" + regex_pattern + "$")


def _component_route_specs() -> List[HttpRouteSpec]:
    specs: List[HttpRouteSpec] = []
    try:
        components = get_domain_component_registry().list()
    except Exception:
        return specs
    for component in components:
        manifest = component.as_dict()
        source_pack_id = str(getattr(component, "source_pack_id", "") or "").strip()
        routes = manifest.get("routes")
        if not isinstance(routes, list):
            continue
        for route in routes:
            if not isinstance(route, dict):
                continue
            method = str(route.get("method") or "").strip().upper()
            pattern = str(route.get("path") or route.get("pattern") or "").strip()
            block_module = str(route.get("block_module") or "").strip()
            function_id = str(
                route.get("function_id")
                or route.get("function_name")
                or route.get("qualified_name")
                or route.get("function")
                or ""
            ).strip()
            function_name = str(
                route.get("function_name")
                or route.get("qualified_name")
                or route.get("function")
                or ""
            ).strip()
            flow_id = str(route.get("flow_id") or "").strip()
            fallback_block_module = str(
                route.get("fallback_block_module") or route.get("fallback_block") or ""
            ).strip()
            legacy_block_module = str(route.get("legacy_block_module") or "").strip()
            handler_name = str(route.get("handler_name") or "").strip()
            if not method or not pattern or not (
                block_module
                or function_id
                or function_name
                or flow_id
                or handler_name
            ):
                continue
            if not _component_route_target_allowed(
                source_pack_id=source_pack_id,
                block_module=block_module,
                fallback_block_module=fallback_block_module,
                handler_name=handler_name,
            ):
                continue
            path_inject = route.get("path_inject")
            defaults = route.get("defaults")
            specs.append(
                HttpRouteSpec(
                    method,
                    pattern,
                    function_id=function_id,
                    legacy_block_module=legacy_block_module,
                    block_module=block_module,
                    function_name=function_name,
                    flow_id=flow_id,
                    fallback_block_module=fallback_block_module,
                    handler_name=handler_name,
                    path_inject=dict(path_inject) if isinstance(path_inject, dict) else {},
                    defaults=dict(defaults) if isinstance(defaults, dict) else {},
                )
            )
    return specs


def component_http_route_specs() -> List[HttpRouteSpec]:
    return list(_component_route_specs())


def component_route_diagnostics() -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for spec in _component_route_specs():
        key = (spec.method, spec.pattern)
        if key in seen:
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "component_route_duplicate",
                    "message": f"duplicate component route {spec.method} {spec.pattern}",
                    "source": "domain component manifests",
                }
            )
        seen.add(key)
    return diagnostics


def _defaultspack_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    try:
        import yaml

        data = yaml.safe_load(text)
    except Exception:
        if path.name == "legacy_http_routes.yaml":
            return _read_legacy_routes_yaml_without_pyyaml(text)
        return {}
    return data if isinstance(data, dict) else {}


def _read_legacy_routes_yaml_without_pyyaml(text: str) -> dict[str, Any]:
    """Parse the simple legacy route allowlist when PyYAML is unavailable."""
    routes: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_legacy_routes = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            if not in_legacy_routes:
                continue
            if current:
                routes.append(current)
            current = {}
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        elif not line.startswith(" "):
            in_legacy_routes = stripped == "legacy_routes:"
            continue
        if not in_legacy_routes:
            continue
        if current is None or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        current[key.strip()] = value.strip().strip("\"'")
    if current:
        routes.append(current)
    return {"legacy_routes": routes} if routes else {}


def _read_flow_yaml(path: Path) -> dict[str, Any]:
    return _read_yaml(path)


def _legacy_http_routes_path() -> Path:
    return _defaultspack_root() / "docs" / "legacy_http_routes.yaml"


@lru_cache(maxsize=1)
def load_legacy_http_route_allowlist() -> dict[tuple[str, str, str], dict[str, Any]]:
    data = _read_yaml(_legacy_http_routes_path())
    allowlist: dict[tuple[str, str, str], dict[str, Any]] = {}
    for route in data.get("legacy_routes") or []:
        if not isinstance(route, dict):
            continue
        method = str(route.get("method") or "").strip().upper()
        pattern = str(route.get("pattern") or "").strip()
        legacy_block_module = str(route.get("legacy_block_module") or "").strip()
        if not method or not pattern or not legacy_block_module:
            continue
        allowlist[(method, pattern, legacy_block_module)] = route
    return allowlist


def require_legacy_route_allowlisted(spec: HttpRouteSpec) -> None:
    legacy_block_module = str(spec.legacy_block_module or "").strip()
    if not legacy_block_module:
        return
    key = (
        str(spec.method or "").upper(),
        str(spec.pattern or "").strip(),
        legacy_block_module,
    )
    if key in load_legacy_http_route_allowlist():
        return
    raise ValueError(
        "legacy HTTP route is not allowlisted: "
        f"{key[0]} {key[1]} -> {legacy_block_module}"
    )


def flow_http_route_specs() -> List[HttpRouteSpec]:
    """Load endpoint -> flow declarations embedded in top-level flow YAML."""
    flows_dir = _defaultspack_root() / "flows"
    specs: List[HttpRouteSpec] = []
    if not flows_dir.is_dir():
        return specs
    for yaml_path in sorted(flows_dir.glob("*.flow.yaml")):
        flow_def = _read_flow_yaml(yaml_path)
        flow_id = str(flow_def.get("flow_id") or yaml_path.name[: -len(".flow.yaml")]).strip()
        if not flow_id:
            continue
        transport = flow_def.get("transport")
        http = transport.get("http") if isinstance(transport, dict) else None
        routes = http.get("routes") if isinstance(http, dict) else None
        if not isinstance(routes, list):
            continue
        for route in routes:
            if not isinstance(route, dict):
                continue
            method = str(route.get("method") or "").strip().upper()
            pattern = str(route.get("path") or route.get("pattern") or "").strip()
            if not method or not pattern:
                continue
            path_inject = route.get("path_inject")
            defaults = route.get("defaults")
            specs.append(
                HttpRouteSpec(
                    method,
                    pattern,
                    flow_id=flow_id,
                    fallback_block_module=str(
                        route.get("fallback_block_module") or route.get("fallback_block") or ""
                    ).strip(),
                    path_inject=dict(path_inject) if isinstance(path_inject, dict) else {},
                    defaults=dict(defaults) if isinstance(defaults, dict) else {},
                )
            )
    return specs


def _dedupe_http_route_specs(groups: list[list[HttpRouteSpec]]) -> list[HttpRouteSpec]:
    result: list[HttpRouteSpec] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for spec in group:
            key = (spec.method, spec.pattern)
            if key in seen:
                continue
            seen.add(key)
            result.append(spec)
    return result


def canonical_http_route_specs(*, include_always_available: bool = True) -> list[HttpRouteSpec]:
    """Return the canonical endpoint -> flow/function/block declaration map.

    Flow YAML declarations win over compatibility fallback entries so normal
    chat ingress can move without changing public HTTP paths.
    """
    flow_specs = flow_http_route_specs()
    fallback_specs = list(_FALLBACK_HTTP_ROUTE_SPECS)
    base_specs = _dedupe_http_route_specs([flow_specs, fallback_specs])
    existing = {(spec.method, spec.pattern) for spec in base_specs}
    component_specs = [
        spec
        for spec in _component_route_specs()
        if (spec.method, spec.pattern) not in existing
    ]
    groups = [base_specs, component_specs]
    if include_always_available:
        groups.append(list(_ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS))
    return _dedupe_http_route_specs(groups)


def flow_http_output_is_compatible(flow_id: str, output: Any, *, fallback_block_module: str = "") -> bool:
    def _has_streamable_events(data: Any) -> bool:
        if not isinstance(data, dict) or not data.get("_sse"):
            return False
        events = data.get("events", [])
        return not isinstance(events, (str, bytes))

    if flow_id == "defaultspack.chat_turn" and fallback_block_module == "blocks.chat.send":
        if not isinstance(output, dict) or output.get("status") != "ok":
            return False
        data = output.get("data")
        if not isinstance(data, dict):
            return False
        return bool(data.get("role") == "assistant" and ("content" in data or "raw_text" in data))
    if flow_id == "defaultspack.chat_stream_turn" and fallback_block_module == "blocks.chat.stream":
        if _has_streamable_events(output):
            return True
        if (
            isinstance(output, dict)
            and output.get("status") == "ok"
            and _has_streamable_events(output.get("data"))
        ):
            return True
        return False
    return True


_FALLBACK_HTTP_ROUTE_SPECS = [
    HttpRouteSpec(
        "POST",
        "/v1/chat/completions",
        flow_id="defaultspack.chat_turn",
        fallback_block_module="blocks.chat.send",
    ),
    HttpRouteSpec("POST", "/api/chat/conversations", block_module="blocks.chat.create_conversation"),
    HttpRouteSpec("GET", "/api/chat/conversations", block_module="blocks.chat.list_conversations"),
    HttpRouteSpec("GET", "/api/chat/conversations/{id}", block_module="blocks.chat.get_conversation", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/chat/search", block_module="blocks.chat.search"),
    HttpRouteSpec("POST", "/api/chat/handoffs", block_module="blocks.conversation.handoff"),
    HttpRouteSpec("POST", "/api/chat/steer", block_module="blocks.conversation.steer"),
    HttpRouteSpec("POST", "/api/chat/guidance", block_module="blocks.conversation.guidance"),
    HttpRouteSpec("PUT", "/api/chat/conversations/{id}", block_module="blocks.chat.update_conversation", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("DELETE", "/api/chat/conversations/{id}", block_module="blocks.chat.delete_conversation", path_inject={"id": "conversation_id"}),
    HttpRouteSpec(
        "POST",
        "/api/chat/conversations/{id}/messages",
        flow_id="defaultspack.chat_turn",
        fallback_block_module="blocks.chat.send",
        path_inject={"id": "conversation_id"},
    ),
    HttpRouteSpec(
        "POST",
        "/api/chat/conversations/{id}/stream",
        flow_id="defaultspack.chat_stream_turn",
        fallback_block_module="blocks.chat.stream",
        path_inject={"id": "conversation_id"},
    ),
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
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/compact", block_module="blocks.chat.compact", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/chat/conversations/{id}/auto-compact", block_module="blocks.chat.auto_compact", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("GET", "/api/chat/conversations/{id}/run-results/{run_id}/browser-screenshots", block_module="blocks.chat.browser_screenshots", path_inject={"id": "conversation_id", "run_id": "run_id"}),
    HttpRouteSpec("GET", "/v1/conversations/{id}/run-results/{run_id}/browser-screenshots", block_module="blocks.chat.browser_screenshots", path_inject={"id": "conversation_id", "run_id": "run_id"}),
    HttpRouteSpec("GET", "/api/chat/conversations/{id}/artifact-file", block_module="blocks.chat.artifact_file", path_inject={"id": "conversation_id"}),
    HttpRouteSpec(
        "GET",
        "/api/human-operator/conversations/{conversation_id}/sessions/{session_id}",
        block_module="blocks.human_operator.page",
        path_inject={"conversation_id": "conversation_id", "session_id": "session_id"},
    ),
    HttpRouteSpec(
        "POST",
        "/api/human-operator/conversations/{conversation_id}/sessions/{session_id}/messages",
        block_module="blocks.human_operator.append_message",
        path_inject={"conversation_id": "conversation_id", "session_id": "session_id"},
    ),
    HttpRouteSpec("POST", "/api/chat/group-storage", block_module="blocks.chat.group_storage"),
    HttpRouteSpec("GET", "/api/integrations/secrets", block_module="blocks.integrations.secrets"),
    HttpRouteSpec("POST", "/api/integrations/secrets", block_module="blocks.integrations.secrets"),
    HttpRouteSpec("POST", "/api/integrations/slack/events", block_module="blocks.integrations.slack"),
    HttpRouteSpec("POST", "/api/integrations/line/webhook", block_module="blocks.integrations.line"),
    HttpRouteSpec("POST", "/api/integrations/discord/interactions", block_module="blocks.integrations.discord"),
    HttpRouteSpec("POST", "/api/integrations/discord/events", block_module="blocks.integrations.discord"),
    HttpRouteSpec("POST", "/api/integrations/p2p/events", block_module="blocks.integrations.p2p"),
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
    HttpRouteSpec("GET", "/api/p2p/status", block_module="blocks.p2p.status"),
    HttpRouteSpec("GET", "/api/p2p/identity", block_module="blocks.p2p.identity"),
    HttpRouteSpec("POST", "/api/p2p/identity/rotate", block_module="blocks.p2p.identity", defaults={"rotate": True}),
    HttpRouteSpec("GET", "/api/p2p/peers", block_module="blocks.p2p.peers"),
    HttpRouteSpec("POST", "/api/p2p/peers", block_module="blocks.p2p.peers"),
    HttpRouteSpec("PUT", "/api/p2p/peers/{peer_id}", block_module="blocks.p2p.peers", path_inject={"peer_id": "peer_id"}),
    HttpRouteSpec("DELETE", "/api/p2p/peers/{peer_id}", block_module="blocks.p2p.peers", path_inject={"peer_id": "peer_id"}),
    HttpRouteSpec("POST", "/api/p2p/pairing/start", block_module="blocks.p2p.pairing_start"),
    HttpRouteSpec("POST", "/api/p2p/pairing/accept", block_module="blocks.p2p.pairing_accept"),
    HttpRouteSpec("POST", "/api/p2p/pairing/reject", block_module="blocks.p2p.pairing_reject"),
    HttpRouteSpec("POST", "/api/p2p/messages/inbound", block_module="blocks.p2p.messages_inbound"),
    HttpRouteSpec("POST", "/api/p2p/messages/send", block_module="blocks.p2p.messages_send"),
    HttpRouteSpec("POST", "/api/agent/execute", block_module="blocks.agent.execute"),
    HttpRouteSpec("POST", "/api/agent/{id}/approve", block_module="blocks.agent.approve", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/agent/{id}/reject", block_module="blocks.agent.reject", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/agent/{id}/cancel", block_module="blocks.agent.cancel", path_inject={"id": "execution_id"}),
    HttpRouteSpec("GET", "/api/agent/company/manifest", block_module="ecosystem.rumi_operations_company_pack.blocks.agent.company.manifest"),
    HttpRouteSpec("GET", "/api/agent/company/status", block_module="ecosystem.rumi_operations_company_pack.blocks.agent.company.status"),
    HttpRouteSpec("POST", "/api/agent/company/bootstrap", block_module="ecosystem.rumi_operations_company_pack.blocks.agent.company.bootstrap"),
    HttpRouteSpec("GET", "/api/agent/mimo-company/manifest", block_module="ecosystem.rumi_operations_company_pack.blocks.agent.mimo_company.manifest"),
    HttpRouteSpec("GET", "/api/agent/mimo-company/status", block_module="ecosystem.rumi_operations_company_pack.blocks.agent.mimo_company.status"),
    HttpRouteSpec("POST", "/api/agent/mimo-company/bootstrap", block_module="ecosystem.rumi_operations_company_pack.blocks.agent.mimo_company.bootstrap"),
    HttpRouteSpec("GET", "/api/agent/self-improvement/status", block_module="blocks.agent.self_improvement_status"),
    HttpRouteSpec("POST", "/api/agent/self-improvement/status", block_module="blocks.agent.self_improvement_status"),
    HttpRouteSpec("POST", "/api/agent/self-improvement/run", block_module="blocks.agent.self_improvement_run"),
    HttpRouteSpec("GET", "/api/agent/self-improvement/report", block_module="blocks.agent.self_improvement_status", defaults={"action": "report"}),
    HttpRouteSpec("GET", "/api/company", block_module="blocks.company.list"),
    HttpRouteSpec("POST", "/api/company", block_module="blocks.company.create"),
    HttpRouteSpec("GET", "/api/company/status", block_module="blocks.company.status"),
    HttpRouteSpec("POST", "/api/company/bootstrap", block_module="blocks.company.bootstrap"),
    HttpRouteSpec("GET", "/api/company/{company_id}", block_module="blocks.company.get", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("PUT", "/api/company/{company_id}", block_module="blocks.company.update", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("DELETE", "/api/company/{company_id}", block_module="blocks.company.delete", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/settings", block_module="blocks.company.settings", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/settings", block_module="blocks.company.settings", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/agents", block_module="blocks.company.agents", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/agents", block_module="blocks.company.agents", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/channels", block_module="blocks.company.channels", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/channels", block_module="blocks.company.channels", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/channels/{channel_id}/messages", block_module="blocks.company.messages", path_inject={"company_id": "company_id", "channel_id": "channel_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/channels/{channel_id}/messages", block_module="blocks.company.messages", path_inject={"company_id": "company_id", "channel_id": "channel_id"}, defaults={"action": "create"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/messages", block_module="blocks.company.messages", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/messages", block_module="blocks.company.messages", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/threads", block_module="blocks.company.threads", path_inject={"company_id": "company_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/threads", block_module="blocks.company.threads", path_inject={"company_id": "company_id"}, defaults={"action": "create"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/threads/{thread_id}", block_module="blocks.company.threads", path_inject={"company_id": "company_id", "thread_id": "thread_id"}, defaults={"action": "get"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/threads/{thread_id}/messages", block_module="blocks.company.messages", path_inject={"company_id": "company_id", "thread_id": "thread_id"}, defaults={"action": "create"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/tasks", block_module="blocks.company.tasks", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/tasks", block_module="blocks.company.tasks", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/dispatch", block_module="blocks.company.dispatch", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/tasks/{task_id}/dispatch", block_module="blocks.company.dispatch", path_inject={"company_id": "company_id", "task_id": "task_id"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/runs", block_module="blocks.company.runs", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/agents/{agent_id}/inbox", block_module="blocks.company.inbox", path_inject={"company_id": "company_id", "agent_id": "agent_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/agents/{agent_id}/inbox/{inbox_id}/consume", block_module="blocks.company.inbox", path_inject={"company_id": "company_id", "agent_id": "agent_id", "inbox_id": "inbox_id"}, defaults={"action": "consume"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/supervisor/tick", block_module="blocks.company.supervisor_tick", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/summaries", block_module="blocks.company.summary", path_inject={"company_id": "company_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/summaries/refresh", block_module="blocks.company.summary", path_inject={"company_id": "company_id"}, defaults={"action": "refresh"}),
    HttpRouteSpec("GET", "/api/company/{company_id}/inbound-routes", block_module="blocks.company.inbound_routes", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/company/{company_id}/inbound-routes", block_module="blocks.company.inbound_routes", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/agent/companies", block_module="blocks.company.list"),
    HttpRouteSpec("POST", "/api/agent/companies", block_module="blocks.company.create"),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}", block_module="blocks.company.get", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("PUT", "/api/agent/companies/{company_id}", block_module="blocks.company.update", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("DELETE", "/api/agent/companies/{company_id}", block_module="blocks.company.delete", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/bootstrap", block_module="blocks.company.bootstrap", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/status", block_module="blocks.company.status", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/settings", block_module="blocks.company.settings", path_inject={"company_id": "company_id"}, defaults={"action": "get"}),
    HttpRouteSpec("PUT", "/api/agent/companies/{company_id}/settings", block_module="blocks.company.settings", path_inject={"company_id": "company_id"}, defaults={"action": "update"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/agents", block_module="blocks.company.agents", path_inject={"company_id": "company_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/agents", block_module="blocks.company.agents", path_inject={"company_id": "company_id"}, defaults={"action": "create"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/agents/{agent_id}", block_module="blocks.company.agents", path_inject={"company_id": "company_id", "agent_id": "agent_id"}, defaults={"action": "get"}),
    HttpRouteSpec("PUT", "/api/agent/companies/{company_id}/agents/{agent_id}", block_module="blocks.company.agents", path_inject={"company_id": "company_id", "agent_id": "agent_id"}, defaults={"action": "update"}),
    HttpRouteSpec("DELETE", "/api/agent/companies/{company_id}/agents/{agent_id}", block_module="blocks.company.agents", path_inject={"company_id": "company_id", "agent_id": "agent_id"}, defaults={"action": "delete"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/channels", block_module="blocks.company.channels", path_inject={"company_id": "company_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/channels", block_module="blocks.company.channels", path_inject={"company_id": "company_id"}, defaults={"action": "create"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/channels/{channel_id}/messages", block_module="blocks.company.messages", path_inject={"company_id": "company_id", "channel_id": "channel_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/channels/{channel_id}/messages", block_module="blocks.company.messages", path_inject={"company_id": "company_id", "channel_id": "channel_id"}, defaults={"action": "create"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/threads", block_module="blocks.company.threads", path_inject={"company_id": "company_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/threads", block_module="blocks.company.threads", path_inject={"company_id": "company_id"}, defaults={"action": "create"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/threads/{thread_id}", block_module="blocks.company.threads", path_inject={"company_id": "company_id", "thread_id": "thread_id"}, defaults={"action": "get"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/threads/{thread_id}/messages", block_module="blocks.company.messages", path_inject={"company_id": "company_id", "thread_id": "thread_id"}, defaults={"action": "create"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/mention", block_module="blocks.company.mention", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/dispatch", block_module="blocks.company.dispatch", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/tasks", block_module="blocks.company.tasks", path_inject={"company_id": "company_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/tasks", block_module="blocks.company.tasks", path_inject={"company_id": "company_id"}, defaults={"action": "create"}),
    HttpRouteSpec("PUT", "/api/agent/companies/{company_id}/tasks/{task_id}", block_module="blocks.company.tasks", path_inject={"company_id": "company_id", "task_id": "task_id"}, defaults={"action": "update"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/tasks/{task_id}/dispatch", block_module="blocks.company.dispatch", path_inject={"company_id": "company_id", "task_id": "task_id"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/runs", block_module="blocks.company.runs", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/agents/{agent_id}/inbox", block_module="blocks.company.inbox", path_inject={"company_id": "company_id", "agent_id": "agent_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/agents/{agent_id}/inbox/{inbox_id}/consume", block_module="blocks.company.inbox", path_inject={"company_id": "company_id", "agent_id": "agent_id", "inbox_id": "inbox_id"}, defaults={"action": "consume"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/supervisor/tick", block_module="blocks.company.supervisor_tick", path_inject={"company_id": "company_id"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/summaries", block_module="blocks.company.summary", path_inject={"company_id": "company_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/summaries/refresh", block_module="blocks.company.summary", path_inject={"company_id": "company_id"}, defaults={"action": "refresh"}),
    HttpRouteSpec("GET", "/api/agent/companies/{company_id}/inbound-routes", block_module="blocks.company.inbound_routes", path_inject={"company_id": "company_id"}, defaults={"action": "list"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/inbound-routes", block_module="blocks.company.inbound_routes", path_inject={"company_id": "company_id"}, defaults={"action": "create"}),
    HttpRouteSpec("PUT", "/api/agent/companies/{company_id}/inbound-routes/{route_id}", block_module="blocks.company.inbound_routes", path_inject={"company_id": "company_id", "route_id": "route_id"}, defaults={"action": "update"}),
    HttpRouteSpec("DELETE", "/api/agent/companies/{company_id}/inbound-routes/{route_id}", block_module="blocks.company.inbound_routes", path_inject={"company_id": "company_id", "route_id": "route_id"}, defaults={"action": "delete"}),
    HttpRouteSpec("POST", "/api/agent/companies/{company_id}/inbound-routes/{route_id}/ingest", block_module="blocks.company.inbound_routes", path_inject={"company_id": "company_id", "route_id": "route_id"}, defaults={"action": "ingest"}),
    HttpRouteSpec("GET", "/api/agent/{id}/status", block_module="blocks.agent.status", path_inject={"id": "execution_id"}),
    HttpRouteSpec("POST", "/api/agent/multi/execute", block_module="blocks.agent.multi_execute"),
    HttpRouteSpec("GET", "/api/agent/multi/{id}/status", block_module="blocks.agent.multi_status", path_inject={"id": "session_id"}),
    HttpRouteSpec("POST", "/api/agent/multi/{id}/message", block_module="blocks.agent.multi_message", path_inject={"id": "session_id"}),
    HttpRouteSpec("POST", "/api/agent/subagent", block_module="blocks.agent.run_subagent"),
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
    HttpRouteSpec("GET", "/api/kanban/boards", block_module="blocks.kanban.api", defaults={"action": "list_boards"}),
    HttpRouteSpec("POST", "/api/kanban/boards/bootstrap", block_module="blocks.kanban.api", defaults={"action": "bootstrap_board"}),
    HttpRouteSpec("GET", "/api/kanban/boards/{board_id}", block_module="blocks.kanban.api", path_inject={"board_id": "board_id"}, defaults={"action": "get_board"}),
    HttpRouteSpec("PUT", "/api/kanban/boards/{board_id}", block_module="blocks.kanban.api", path_inject={"board_id": "board_id"}, defaults={"action": "update_board"}),
    HttpRouteSpec("POST", "/api/kanban/boards/{board_id}/cards", block_module="blocks.kanban.api", path_inject={"board_id": "board_id"}, defaults={"action": "create_card"}),
    HttpRouteSpec("POST", "/api/kanban/boards/{board_id}/columns", block_module="blocks.kanban.api", path_inject={"board_id": "board_id"}, defaults={"action": "create_column"}),
    HttpRouteSpec("POST", "/api/kanban/boards/{board_id}/sync-runs", block_module="blocks.kanban.api", path_inject={"board_id": "board_id"}, defaults={"action": "sync_runs"}),
    HttpRouteSpec("POST", "/api/kanban/boards/{board_id}/import-conversation", block_module="blocks.kanban.api", path_inject={"board_id": "board_id"}, defaults={"action": "import_conversation"}),
    HttpRouteSpec("PUT", "/api/kanban/cards/{card_id}", block_module="blocks.kanban.api", path_inject={"card_id": "card_id"}, defaults={"action": "update_card"}),
    HttpRouteSpec("DELETE", "/api/kanban/cards/{card_id}", block_module="blocks.kanban.api", path_inject={"card_id": "card_id"}, defaults={"action": "delete_card"}),
    HttpRouteSpec("POST", "/api/kanban/cards/{card_id}/move", block_module="blocks.kanban.api", path_inject={"card_id": "card_id"}, defaults={"action": "move_card"}),
    HttpRouteSpec("POST", "/api/kanban/cards/{card_id}/agent/start", block_module="blocks.kanban.api", path_inject={"card_id": "card_id"}, defaults={"action": "agent_start"}),
    HttpRouteSpec("GET", "/api/kanban/cards/{card_id}/agent/status", block_module="blocks.kanban.api", path_inject={"card_id": "card_id"}, defaults={"action": "agent_status"}),
    HttpRouteSpec("POST", "/api/kanban/cards/{card_id}/agent/ready", block_module="blocks.kanban.api", path_inject={"card_id": "card_id"}, defaults={"action": "agent_ready"}),
    HttpRouteSpec("POST", "/api/kanban/cards/{card_id}/agent/apply", block_module="blocks.kanban.api", path_inject={"card_id": "card_id"}, defaults={"action": "agent_apply"}),
    HttpRouteSpec("POST", "/api/kanban/cards/{card_id}/agent/dismiss", block_module="blocks.kanban.api", path_inject={"card_id": "card_id"}, defaults={"action": "agent_dismiss"}),
    HttpRouteSpec("PUT", "/api/kanban/columns/{column_id}", block_module="blocks.kanban.api", path_inject={"column_id": "column_id"}, defaults={"action": "update_column"}),
    HttpRouteSpec("DELETE", "/api/kanban/columns/{column_id}", block_module="blocks.kanban.api", path_inject={"column_id": "column_id"}, defaults={"action": "delete_column"}),
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
    HttpRouteSpec("GET", "/api/coding/rumi-log", block_module="blocks.coding.rumi_log", path_inject={"_method": "GET"}),
    HttpRouteSpec("POST", "/api/coding/rumi-log", block_module="blocks.coding.rumi_log", path_inject={"_method": "POST"}),
    HttpRouteSpec("GET", "/api/coding/checkpoints", block_module="blocks.coding.file_checkpoint", path_inject={"_method": "GET"}),
    HttpRouteSpec("POST", "/api/coding/checkpoints", block_module="blocks.coding.file_checkpoint", path_inject={"_method": "POST"}),
    HttpRouteSpec("GET", "/api/coding/approvals", block_module="blocks.coding.approval_list"),
    HttpRouteSpec("POST", "/api/coding/approvals/approve", block_module="blocks.coding.approval_approve"),
    HttpRouteSpec("POST", "/api/coding/approvals/deny", block_module="blocks.coding.approval_deny"),
    HttpRouteSpec("GET", "/api/authority/requests", handler_name="_handle_authority_requests"),
    HttpRouteSpec("GET", "/api/authority/requests/{request_id}", handler_name="_handle_authority_request"),
    HttpRouteSpec("POST", "/api/authority/test/request", handler_name="_handle_authority_test_request"),
    HttpRouteSpec("POST", "/api/authority/requests/{request_id}/approve", handler_name="_handle_authority_approve"),
    HttpRouteSpec("POST", "/api/authority/requests/{request_id}/deny", handler_name="_handle_authority_deny"),
    HttpRouteSpec("POST", "/api/coding/github/pr", block_module="blocks.coding.github_pr_read"),
    HttpRouteSpec("POST", "/api/coding/github/issue", block_module="blocks.coding.github_issue_read"),
    HttpRouteSpec("POST", "/api/coding/github/ci", block_module="blocks.coding.github_ci_status"),
    HttpRouteSpec("POST", "/api/coding/agent/sessions", block_module="blocks.agent.coding_session_create"),
    HttpRouteSpec("GET", "/api/coding/agent/sessions/status", block_module="blocks.agent.coding_session_status"),
    HttpRouteSpec("GET", "/api/coding/agent/sessions/merge-report", block_module="blocks.agent.coding_session_merge_report"),
    HttpRouteSpec("GET", "/api/coding/workspaces", block_module="blocks.coding.workspace.list"),
    HttpRouteSpec("POST", "/api/coding/workspaces", block_module="blocks.coding.workspace.create"),
    HttpRouteSpec("GET", "/api/coding/workspaces/get", block_module="blocks.coding.workspace.get"),
    HttpRouteSpec("POST", "/api/coding/workspaces/update", block_module="blocks.coding.workspace.update"),
    HttpRouteSpec("POST", "/api/coding/workspaces/select", block_module="blocks.coding.workspace.select"),
    HttpRouteSpec("POST", "/api/coding/workspaces/trust", block_module="blocks.coding.workspace.trust"),
    HttpRouteSpec("GET", "/api/coding/workspaces/{workspace_id}", block_module="blocks.coding.workspace.get", path_inject={"workspace_id": "workspace_id"}),
    HttpRouteSpec("PUT", "/api/coding/workspaces/{workspace_id}", block_module="blocks.coding.workspace.update", path_inject={"workspace_id": "workspace_id"}),
    HttpRouteSpec("POST", "/api/coding/workspaces/{workspace_id}/select", block_module="blocks.coding.workspace.select", path_inject={"workspace_id": "workspace_id"}),
    HttpRouteSpec("POST", "/api/coding/workspaces/{workspace_id}/trust", block_module="blocks.coding.workspace.trust", path_inject={"workspace_id": "workspace_id"}),
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
    HttpRouteSpec("POST", "/api/prompts/lint", block_module="blocks.prompt.lint_prompt"),
    HttpRouteSpec("POST", "/api/prompts/compact", block_module="blocks.prompt.compact_prompt"),
    HttpRouteSpec("GET", "/api/tools", block_module="blocks.tool.list"),
    HttpRouteSpec("GET", "/api/tools/mcp", block_module="blocks.tool.mcp_list"),
    HttpRouteSpec("POST", "/api/tools/mcp", block_module="blocks.tool.mcp_registry"),
    HttpRouteSpec("DELETE", "/api/tools/mcp", block_module="blocks.tool.mcp_registry"),
    HttpRouteSpec("POST", "/api/tools/mcp/connect", block_module="blocks.tool.mcp_connect"),
    HttpRouteSpec("GET", "/api/browser/artifacts", block_module="blocks.browser.artifacts"),
    HttpRouteSpec("POST", "/api/tools/invoke", block_module="blocks.tool.invoke"),
    HttpRouteSpec("POST", "/api/tools/browser-computer", block_module="blocks.tool.browser_computer"),
    HttpRouteSpec("POST", "/api/tools/browser-companion/bridge/poll", block_module="blocks.tool.browser_companion_bridge_poll"),
    HttpRouteSpec("POST", "/api/tools/browser-companion/bridge/result", block_module="blocks.tool.browser_companion_bridge_result"),
    HttpRouteSpec("POST", "/api/tools/create", block_module="blocks.tool.create"),
    HttpRouteSpec("GET", "/api/tools/permissions", block_module="blocks.tool.permissions"),
    HttpRouteSpec("PUT", "/api/tools/permissions", block_module="blocks.tool.permissions", defaults={"_handler": "run_put"}),
    HttpRouteSpec("POST", "/api/tools/permissions/check", block_module="blocks.tool.permissions", defaults={"_handler": "run_check"}),
    HttpRouteSpec("GET", "/api/tools/{name}/permissions", block_module="blocks.tool.permissions", path_inject={"name": "name"}),
    HttpRouteSpec("PUT", "/api/tools/{name}/permissions", block_module="blocks.tool.permissions", path_inject={"name": "name"}, defaults={"_handler": "run_put"}),
    HttpRouteSpec("PUT", "/api/tools/{name}", block_module="blocks.tool.update", path_inject={"name": "name"}),
    HttpRouteSpec("DELETE", "/api/tools/{name}", block_module="blocks.tool.delete", path_inject={"name": "name"}),
    HttpRouteSpec("GET", "/api/tools/{name}/export", block_module="blocks.tool.export", path_inject={"name": "name"}),
    HttpRouteSpec("POST", "/api/scheduler/create", block_module="blocks.scheduler.create"),
    HttpRouteSpec("GET", "/api/scheduler/list", block_module="blocks.scheduler.list"),
    HttpRouteSpec("PUT", "/api/scheduler/{id}", block_module="blocks.scheduler.update", path_inject={"id": "job_id"}),
    HttpRouteSpec("DELETE", "/api/scheduler/{id}", block_module="blocks.scheduler.delete", path_inject={"id": "job_id"}),
    HttpRouteSpec("POST", "/api/scheduler/{id}/pause", block_module="blocks.scheduler.pause", path_inject={"id": "job_id"}),
    HttpRouteSpec("POST", "/api/scheduler/{id}/resume", block_module="blocks.scheduler.resume", path_inject={"id": "job_id"}),
    HttpRouteSpec("POST", "/api/scheduler/{id}/run-now", block_module="blocks.scheduler.run_now", path_inject={"id": "job_id"}),
    HttpRouteSpec("POST", "/api/scheduler/tick", block_module="blocks.scheduler.tick"),
    HttpRouteSpec("GET", "/api/scheduler/status", block_module="blocks.scheduler.status"),
    HttpRouteSpec("GET", "/api/recording/devices", block_module="blocks.recording.capture", defaults={"action": "list_devices"}),
    HttpRouteSpec("POST", "/api/recording/capture", block_module="blocks.recording.capture"),
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
    HttpRouteSpec("GET", "/api/ai/oauth", block_module="blocks.ai.oauth"),
    HttpRouteSpec("POST", "/api/ai/oauth", block_module="blocks.ai.oauth"),
    HttpRouteSpec("GET", "/api/ai/oauth/{provider_id}/callback", block_module="blocks.ai.oauth", path_inject={"provider_id": "provider_id"}),
    HttpRouteSpec("GET", "/api/ai/catalog", block_module="blocks.ai.catalog"),
    HttpRouteSpec("GET", "/api/ai/providers", block_module="blocks.ai.providers"),
    HttpRouteSpec("GET", "/api/ai/models", block_module="blocks.ai.models"),
    HttpRouteSpec("POST", "/api/ai/models/search", block_module="blocks.ai.search_models"),
    HttpRouteSpec("POST", "/api/ai/models/capabilities", block_module="blocks.ai.get_model_capabilities"),
    HttpRouteSpec("POST", "/api/ai/models/recommend", block_module="blocks.ai.recommend_model"),
    HttpRouteSpec("POST", "/api/ai/models/route", block_module="blocks.ai.route_model"),
    HttpRouteSpec("GET", "/api/ai/profiles", block_module="blocks.ai.profiles"),
    HttpRouteSpec("POST", "/api/vision/describe-images", block_module="blocks.vision.describe_images"),
    HttpRouteSpec("GET", "/api/ui/catalog", block_module="blocks.ui.catalog"),
    HttpRouteSpec("GET", "/api/ui/settings", block_module="blocks.ui.settings"),
    HttpRouteSpec("PUT", "/api/ui/settings", block_module="blocks.ui.settings"),
    HttpRouteSpec("GET", "/api/ui/commands", block_module="blocks.ui.commands"),
    HttpRouteSpec("POST", "/api/ui/commands/execute", block_module="blocks.ui.commands"),
    HttpRouteSpec("POST", "/api/ui/clipboard", block_module="blocks.ui.clipboard"),
    HttpRouteSpec("POST", "/api/ui/client-events", block_module="blocks.ui.client_events"),
    HttpRouteSpec("GET", "/api/ui/conversations/{id}/preview", block_module="blocks.ui.conversation_preview", path_inject={"id": "conversation_id"}),
    HttpRouteSpec("POST", "/api/ui/select-directory", block_module="blocks.ui.select_directory"),
]

_ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS = [
    HttpRouteSpec("GET", "/api/health", handler_name="_handle_health"),
    HttpRouteSpec("GET", "/api/context", handler_name="_handle_context_info"),
    HttpRouteSpec("GET", "/api/desktop-system-info", handler_name="_handle_desktop_system_info"),
    HttpRouteSpec("GET", "/", handler_name="_handle_chat_redirect"),
    HttpRouteSpec("GET", "/chat", handler_name="_handle_static"),
    HttpRouteSpec("GET", "/coding", handler_name="_handle_static"),
    HttpRouteSpec("GET", "/approval", handler_name="_handle_static"),
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
    ordered_specs = [
        spec
        for _, spec in sorted(
            enumerate(specs),
            key=lambda item: http_route_sort_key(item[1].method, item[1].pattern, item[0]),
        )
    ]
    for spec in ordered_specs:
        compiled = compile_http_route_pattern(spec.pattern)
        require_legacy_route_allowlisted(spec)
        if spec.flow_id:
            def _handler(
                request_data,
                path_params,
                *,
                flow_id=spec.flow_id,
                fallback_block_module=spec.legacy_block_module or spec.fallback_block_module,
                path_inject=dict(spec.path_inject),
                route_defaults=dict(spec.defaults),
                route_method=spec.method,
            ):
                payload = dict(request_data or {})
                payload.update(route_defaults)
                payload["_method"] = route_method
                return server._invoke_flow_route(
                    flow_id,
                    payload,
                    path_params,
                    path_inject,
                    fallback_block_module=fallback_block_module,
                )
            handler = _handler
        elif spec.function_id:
            def _handler(
                request_data,
                path_params,
                *,
                function_name=spec.function_id,
                fallback_block_module=spec.legacy_block_module or spec.fallback_block_module,
                path_inject=dict(spec.path_inject),
                route_defaults=dict(spec.defaults),
                route_method=spec.method,
            ):
                payload = dict(request_data or {})
                payload.update(route_defaults)
                payload["_method"] = route_method
                function_route = getattr(server, "_invoke_function_route", None)
                if callable(function_route):
                    return function_route(
                        function_name,
                        payload,
                        path_params,
                        path_inject,
                        fallback_block_module=fallback_block_module,
                    )
                if fallback_block_module:
                    return server._invoke_fallback_block(
                        fallback_block_module,
                        payload,
                        path_params,
                        path_inject,
                    )
                raise AttributeError("_invoke_function_route")
            handler = _handler
        elif spec.legacy_block_module or spec.block_module:
            def _handler(
                request_data,
                path_params,
                *,
                block_module=spec.legacy_block_module or spec.block_module,
                path_inject=dict(spec.path_inject),
                route_defaults=dict(spec.defaults),
                route_method=spec.method,
            ):
                payload = dict(request_data or {})
                payload.update(route_defaults)
                payload["_method"] = route_method
                return server._invoke_fallback_block(
                    block_module,
                    payload,
                    path_params,
                    path_inject,
                )
            handler = _handler
        else:
            handler = getattr(server, spec.handler_name)
        try:
            setattr(handler, "__rumi_route_pattern__", spec.pattern)
        except Exception:
            pass
        routes.append((spec.method, compiled, handler, "fallback", dict(spec.path_inject)))
    return routes


def build_always_available_http_routes(server: Any):
    return build_http_routes_from_specs(server, _ALWAYS_AVAILABLE_HTTP_ROUTE_SPECS)


def build_fallback_http_routes(server: Any):
    return build_http_routes_from_specs(
        server,
        canonical_http_route_specs(include_always_available=True),
    )
