from __future__ import annotations

import copy
from typing import Any

from core_runtime.ai_input_graph_builder import MODEL_INPUT_NODE_ID, build_ai_input_graph_response
from core_runtime.ai_input_models import normalize_ai_input_config
from core_runtime.ai_input_trace_store import AiInputTraceStore
from core_runtime.profile_paths import active_profile_id
from core_runtime.profile_runtime_selection import apply_profile_graph_selection
from core_runtime.profile_workspace import ProfileWorkspaceManager, validate_profile_id


def active_prompt_summary(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    profile = _load_profile(profile_id)
    request_context = _request_context(data)
    response = build_ai_input_graph_response(
        profile,
        include_text=bool(data.get("include_text", False)),
        request_context=request_context,
    )
    usage = prompt_usage_from_graph_response(
        response,
        conversation_id=str(data.get("conversation_id") or request_context.get("conversation_id") or ""),
        run_id=str(data.get("run_id") or "active"),
        trace_id=str(data.get("trace_id") or "active"),
        include_text=bool(data.get("include_text", False)),
    )
    return {
        "profile_id": profile_id,
        "conversation_id": usage.get("conversation_id", ""),
        "summary": usage,
        "segments": usage.get("segments", []),
        "active_segments": usage.get("active_segments", []),
        "disabled_segments": usage.get("disabled_segments", []),
        "token_estimate": usage.get("token_estimate", {}),
        "graph": response.get("graph", {}),
        "gate_decisions": response.get("gate_decisions", []),
        "diagnostics": response.get("diagnostics", []),
        "ai_input": response.get("ai_input", {}),
    }


def list_prompt_traces(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    try:
        limit = int(data.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    traces = AiInputTraceStore().list_traces(profile_id, limit=limit)
    conversation_id = str(data.get("conversation_id") or "").strip()
    if conversation_id:
        traces = [trace for trace in traces if str(trace.get("conversation_id") or "") == conversation_id]
    return {"profile_id": profile_id, "traces": traces, "count": len(traces)}


def get_prompt_trace(input_data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    trace_id = str(data.get("trace_id") or data.get("id") or "").strip()
    if not trace_id:
        raise ValueError("trace_id is required")
    trace = AiInputTraceStore().get_trace(profile_id, trace_id)
    if trace is None:
        return None
    return {
        "profile_id": profile_id,
        "trace": trace,
        "prompt_usage": prompt_usage_from_trace(trace, include_text=bool(data.get("include_text", True))),
    }


def toggle_prompt_edge(input_data: dict[str, Any] | None = None, *, preview: bool = False) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    profile_id = _resolve_profile_id(data.get("profile_id"))
    edge_id = str(data.get("edge_id") or "").strip()
    if not edge_id:
        raise ValueError("edge_id is required")
    enabled = bool(data.get("enabled", True))
    profile = _load_profile(profile_id)
    request_context = _request_context(data)
    current = build_ai_input_graph_response(profile, include_text=False, request_context=request_context)
    edge = _find_edge(current.get("graph"), edge_id)
    if edge is None:
        raise ValueError(f"edge not found: {edge_id}")
    source_node = _find_node(current.get("graph"), str(edge.get("from_id") or ""))
    source_metadata = source_node.get("metadata") if isinstance(source_node, dict) and isinstance(source_node.get("metadata"), dict) else {}
    allow_disable = bool(source_metadata.get("metadata", source_metadata).get("allow_disable", True))
    if not enabled and not allow_disable:
        raise PermissionError("This prompt edge cannot be disabled.")

    patched_profile = _profile_with_edge_state(profile, edge_id=edge_id, enabled=enabled)
    response = build_ai_input_graph_response(
        patched_profile,
        include_text=bool(data.get("include_text", False)),
        request_context=request_context,
    )
    if not preview:
        raw_profile = _load_raw_profile(profile_id)
        ProfileWorkspaceManager().save_profile_yaml(
            profile_id,
            _profile_with_edge_state(raw_profile, edge_id=edge_id, enabled=enabled),
        )
    return {
        "profile_id": profile_id,
        "edge_id": edge_id,
        "enabled": enabled,
        "preview": preview,
        "ai_input": response.get("ai_input", {}),
        "summary": prompt_usage_from_graph_response(
            response,
            conversation_id=str(data.get("conversation_id") or ""),
            run_id=str(data.get("run_id") or "toggle"),
            trace_id="preview_toggle" if preview else "active",
            include_text=bool(data.get("include_text", False)),
        ),
    }


def prompt_usage_from_trace(trace: dict[str, Any], *, include_text: bool = True) -> dict[str, Any]:
    effective = trace.get("effective_input") if isinstance(trace.get("effective_input"), dict) else {}
    usage = _usage_payload(
        profile_id=str(trace.get("profile_id") or effective.get("profile_id") or ""),
        conversation_id=str(trace.get("conversation_id") or ""),
        run_id=str(trace.get("run_id") or ""),
        trace_id=str(trace.get("trace_id") or ""),
        effective=effective,
        graph=trace.get("graph") if isinstance(trace.get("graph"), dict) else {},
        token_estimate=trace.get("token_estimate") if isinstance(trace.get("token_estimate"), dict) else {},
        gate_decisions=trace.get("gate_decisions") if isinstance(trace.get("gate_decisions"), list) else [],
        diagnostics=trace.get("diagnostics") if isinstance(trace.get("diagnostics"), list) else [],
        blocked=trace.get("blocked") if isinstance(trace.get("blocked"), list) else [],
        include_text=include_text,
    )
    for segment in trace.get("runtime_prompt_segments", []) if isinstance(trace.get("runtime_prompt_segments"), list) else []:
        if isinstance(segment, dict):
            usage = append_runtime_prompt_segment(usage, segment)
    return usage


def prompt_usage_from_graph_response(
    response: dict[str, Any],
    *,
    conversation_id: str = "",
    run_id: str = "",
    trace_id: str = "",
    include_text: bool = True,
) -> dict[str, Any]:
    effective = response.get("effective_input") if isinstance(response.get("effective_input"), dict) else {}
    return _usage_payload(
        profile_id=str(response.get("profile_id") or effective.get("profile_id") or ""),
        conversation_id=conversation_id,
        run_id=run_id,
        trace_id=trace_id,
        effective=effective,
        graph=response.get("graph") if isinstance(response.get("graph"), dict) else {},
        token_estimate=response.get("token_estimate") if isinstance(response.get("token_estimate"), dict) else {},
        gate_decisions=response.get("gate_decisions") if isinstance(response.get("gate_decisions"), list) else [],
        diagnostics=response.get("diagnostics") if isinstance(response.get("diagnostics"), list) else [],
        blocked=[],
        include_text=include_text,
    )


def compact_prompt_usage_for_metadata(usage: dict[str, Any]) -> dict[str, Any]:
    segments = []
    for segment in usage.get("segments", []) if isinstance(usage.get("segments"), list) else []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "")
        compact = {
            key: copy.deepcopy(value)
            for key, value in segment.items()
            if key not in {"text", "schema"}
        }
        if text and not str(compact.get("preview") or "").strip():
            compact["preview"] = " ".join(text.split())[:280]
        if text:
            compact["has_full_text"] = True
        segments.append(compact)
    return {
        "trace_id": usage.get("trace_id"),
        "profile_id": usage.get("profile_id"),
        "conversation_id": usage.get("conversation_id"),
        "run_id": usage.get("run_id"),
        "active_count": usage.get("active_count", 0),
        "disabled_count": usage.get("disabled_count", 0),
        "token_estimate": copy.deepcopy(usage.get("token_estimate", {})),
        "segments": segments,
        "active_segments": [item for item in segments if item.get("status") == "active"],
        "disabled_segments": [item for item in segments if item.get("status") != "active"],
    }


def append_runtime_prompt_segment(usage: dict[str, Any] | None, segment: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(usage) if isinstance(usage, dict) else {}
    segments = payload.get("segments") if isinstance(payload.get("segments"), list) else []
    item = dict(segment)
    item.setdefault("status", "active")
    item.setdefault("enabled", True)
    item.setdefault("allow_disable", False)
    item.setdefault("editable", False)
    item.setdefault("readonly_reason", "runtime generated")
    item.setdefault("source_chain", [])
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    source_type = str(item.get("source_type") or metadata.get("source_type") or "")
    port = str(item.get("port") or "system")
    kind = str(item.get("kind") or _segment_kind(str(item.get("id") or ""), source_type, port))
    item["kind"] = kind
    item["reason"] = str(item.get("reason") or _reason_for_segment(item, metadata, {}))
    item.update(_segment_extras(item, item, metadata, {}))
    segments.append(item)
    payload["segments"] = segments
    payload["active_segments"] = [entry for entry in segments if entry.get("status") == "active"]
    payload["disabled_segments"] = [entry for entry in segments if entry.get("status") != "active"]
    payload["active_count"] = len(payload["active_segments"])
    payload["disabled_count"] = len(payload["disabled_segments"])
    token_estimate = payload.get("token_estimate") if isinstance(payload.get("token_estimate"), dict) else {}
    by_port = token_estimate.get("by_port") if isinstance(token_estimate.get("by_port"), dict) else {}
    port = str(item.get("port") or "system")
    tokens = int(item.get("tokens") or 0)
    by_port[port] = int(by_port.get(port) or 0) + tokens
    token_estimate["by_port"] = by_port
    token_estimate["total"] = int(token_estimate.get("total") or 0) + tokens
    payload["token_estimate"] = token_estimate
    return payload


def _usage_payload(
    *,
    profile_id: str,
    conversation_id: str,
    run_id: str,
    trace_id: str,
    effective: dict[str, Any],
    graph: dict[str, Any],
    token_estimate: dict[str, Any],
    gate_decisions: list[Any],
    diagnostics: list[Any],
    blocked: list[Any],
    include_text: bool,
) -> dict[str, Any]:
    active: list[dict[str, Any]] = []
    for port, key in (
        ("system", "system_segments"),
        ("developer", "developer_segments"),
        ("context", "context_segments"),
        ("tools", "tool_schemas"),
    ):
        for segment in effective.get(key) if isinstance(effective.get(key), list) else []:
            if isinstance(segment, dict):
                active.append(_segment_payload(segment, port=port, status="active", graph=graph, include_text=include_text))
    policy = effective.get("policy") if isinstance(effective.get("policy"), dict) else {}
    for segment in policy.get("segments") if isinstance(policy.get("segments"), list) else []:
        if isinstance(segment, dict):
            active.append(_segment_payload(segment, port="policy", status="active", graph=graph, include_text=include_text))

    disabled = [
        _disabled_payload(segment, graph=graph, include_text=include_text)
        for segment in effective.get("disabled_segments", [])
        if isinstance(segment, dict)
    ]
    segments = [*active, *disabled]
    return {
        "trace_id": trace_id,
        "profile_id": profile_id,
        "conversation_id": conversation_id,
        "run_id": run_id,
        "segments": segments,
        "active_segments": active,
        "disabled_segments": disabled,
        "active_count": len(active),
        "disabled_count": len(disabled),
        "token_estimate": token_estimate,
        "gate_decisions": gate_decisions,
        "diagnostics": diagnostics,
        "blocked": blocked,
        "source_counts": _source_counts(segments),
    }


def _segment_payload(
    segment: dict[str, Any],
    *,
    port: str,
    status: str,
    graph: dict[str, Any],
    include_text: bool,
) -> dict[str, Any]:
    metadata = segment.get("metadata") if isinstance(segment.get("metadata"), dict) else {}
    segment_id = str(segment.get("id") or "")
    edge_id = _edge_id_for(segment_id, port)
    graph_edge = _find_edge(graph, edge_id) or {}
    allow_disable = bool(metadata.get("allow_disable", True))
    source_type = str(segment.get("source_type") or metadata.get("source_type") or ("tool_schema" if port == "tools" else "prompt"))
    kind = _segment_kind(segment_id, source_type, port)
    payload = {
        "id": segment_id,
        "edge_id": edge_id,
        "prompt_id": str(metadata.get("prompt_id") or metadata.get("resolved_prompt_id") or segment.get("tool_id") or segment.get("name") or segment_id.removeprefix("prompt:")),
        "label": _segment_label(segment, metadata),
        "kind": kind,
        "port": port,
        "status": status,
        "enabled": status == "active",
        "source": str(segment.get("source") or metadata.get("source") or ""),
        "source_type": source_type,
        "source_chain": metadata.get("source_chain") if isinstance(metadata.get("source_chain"), list) else [],
        "tokens": int(segment.get("tokens") or 0),
        "reason": str(segment.get("reason") or _reason_for_segment({"kind": kind, "port": port, "status": status, "source_type": source_type, "edge_id": edge_id, "source": segment.get("source")}, metadata, graph_edge)),
        "allow_disable": allow_disable,
        "editable": _is_editable(source_type, metadata),
        "readonly_reason": _readonly_reason(source_type, metadata),
        "preview": str(segment.get("preview") or ""),
        "metadata": copy.deepcopy(metadata),
        "edge": graph_edge,
    }
    payload.update(_segment_extras(payload, segment, metadata, graph_edge))
    if include_text and "text" in segment:
        payload["text"] = str(segment.get("text") or "")
    if include_text and "schema" in segment:
        payload["schema"] = copy.deepcopy(segment.get("schema"))
    return payload


def _disabled_payload(segment: dict[str, Any], *, graph: dict[str, Any], include_text: bool) -> dict[str, Any]:
    metadata = segment.get("metadata") if isinstance(segment.get("metadata"), dict) else {}
    source_type = str(segment.get("source_type") or metadata.get("source_type") or ("tool_schema" if str(segment.get("id") or "").startswith("tool_schema:") else "prompt"))
    segment_id = str(segment.get("id") or "")
    port = _port_for_segment(segment_id, source_type)
    edge_id = _edge_id_for(segment_id, port)
    graph_edge = _find_edge(graph, edge_id) or {}
    reason = str(segment.get("reason") or "")
    status = "budget-dropped" if reason == "budget_exceeded" else "gated" if reason == "edge_disabled_or_gate_blocked" and not _edge_disabled_by_user(graph_edge) else "disabled"
    payload = _segment_payload(
        {**segment, "source_type": source_type},
        port=port,
        status=status,
        graph=graph,
        include_text=include_text,
    )
    payload["enabled"] = False
    payload["reason"] = _disabled_reason_label(reason, graph_edge)
    return payload


def _resolve_profile_id(value: Any = None) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        candidate = str(active_profile_id() or "").strip()
    if not candidate:
        candidate = "defaultspack.startup"
    return validate_profile_id(candidate)


def _load_profile(profile_id: str) -> dict[str, Any]:
    profile = _load_raw_profile(profile_id)
    try:
        return apply_profile_graph_selection(profile)
    except Exception:
        return profile


def _load_raw_profile(profile_id: str) -> dict[str, Any]:
    manager = ProfileWorkspaceManager()
    profile = manager.load_profile_yaml(profile_id)
    if not isinstance(profile, dict) or not profile:
        profile = {
            "version": 1,
            "profile_id": profile_id,
            "name": profile_id,
            "base_pack": "defaultspack",
            "default_prompt_id": "default_chat",
            "metadata": {},
            "policy": {},
        }
    profile.setdefault("profile_id", profile_id)
    profile.setdefault("base_pack", "defaultspack")
    return profile


def _request_context(data: dict[str, Any]) -> dict[str, Any]:
    context = data.get("request_context") if isinstance(data.get("request_context"), dict) else {}
    merged = dict(context)
    for key in ("conversation_id", "run_id", "message", "user_text", "knowledge_text", "memory_text"):
        if key in data and data.get(key) is not None:
            merged[key] = data.get(key)
    return merged


def _profile_with_edge_state(profile: dict[str, Any], *, edge_id: str, enabled: bool) -> dict[str, Any]:
    patched = copy.deepcopy(profile)
    metadata = patched.get("metadata") if isinstance(patched.get("metadata"), dict) else {}
    raw_ai_input = metadata.get("ai_input") if isinstance(metadata.get("ai_input"), dict) else {}
    ai_input = copy.deepcopy(raw_ai_input)
    disabled_edges = list(normalize_ai_input_config(raw_ai_input).get("disabled_edges") or [])
    if enabled:
        disabled_edges = [item for item in disabled_edges if item != edge_id]
    elif edge_id not in disabled_edges:
        disabled_edges.append(edge_id)
    ai_input["disabled_edges"] = disabled_edges
    metadata["ai_input"] = ai_input
    patched["metadata"] = metadata
    return patched


def _find_edge(graph: Any, edge_id: str) -> dict[str, Any] | None:
    edges = graph.get("edges") if isinstance(graph, dict) else []
    for edge in edges if isinstance(edges, list) else []:
        if isinstance(edge, dict) and edge.get("id") == edge_id:
            return edge
    return None


def _find_node(graph: Any, node_id: str) -> dict[str, Any] | None:
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    for node in nodes if isinstance(nodes, list) else []:
        if isinstance(node, dict) and node.get("id") == node_id:
            return node
    return None


def _edge_id_for(segment_id: str, port: str) -> str:
    return f"edge:{segment_id}->{MODEL_INPUT_NODE_ID}.{port}"


def _port_for_segment(segment_id: str, source_type: str) -> str:
    if segment_id.startswith("tool_schema:"):
        return "tools"
    if source_type in {"memory_source", "retrieval_source"}:
        return "context"
    if source_type in {"profile_policy", "api_route"} or segment_id.startswith("policy:"):
        return "policy"
    return "system"


def _segment_label(segment: dict[str, Any], metadata: dict[str, Any]) -> str:
    return str(
        segment.get("name")
        or metadata.get("prompt_id")
        or metadata.get("resolved_prompt_id")
        or segment.get("tool_id")
        or segment.get("id")
        or "Prompt segment"
    )


def _segment_kind(segment_id: str, source_type: str, port: str) -> str:
    if segment_id.startswith("skill:") or source_type == "skill":
        return "skill"
    if port == "tools" or segment_id.startswith("tool_schema:"):
        return "tool-schema"
    if source_type == "memory_source":
        return "memory"
    if source_type == "retrieval_source":
        return "context"
    if source_type in {"profile_override", "profile_snapshot", "profile_prompt"}:
        return "profile"
    if source_type in {"extension", "canonical_fallback"}:
        return "extension"
    if source_type in {"pack", "pack_default"}:
        return "pack"
    if source_type == "component":
        return "component"
    if source_type == "api_route":
        return "context"
    return "prompt"


def _segment_extras(
    payload: dict[str, Any],
    segment: dict[str, Any],
    metadata: dict[str, Any],
    edge: dict[str, Any],
) -> dict[str, Any]:
    kind = str(payload.get("kind") or "prompt")
    status = str(payload.get("status") or "available")
    source_type = str(payload.get("source_type") or "")
    port = str(payload.get("port") or "")
    reason = str(payload.get("reason") or _reason_for_segment(payload, metadata, edge))
    extras: dict[str, Any] = {
        "reason": reason,
        "explanation": reason,
        "input_role": _input_role(kind, port),
        "activation_detail": _activation_detail(payload, metadata, edge),
        "safety_boundary": _safety_boundary(kind),
        "source_priority": _source_priority(source_type),
    }
    tool_signal = _tool_signal(payload, segment, metadata)
    if tool_signal:
        extras["tool_signal"] = tool_signal
    skill_signal = _skill_signal(payload, metadata)
    if skill_signal:
        extras["skill_signal"] = skill_signal
    return extras


def _reason_for_segment(segment: dict[str, Any], metadata: dict[str, Any], edge: dict[str, Any]) -> str:
    status = str(segment.get("status") or "available")
    kind = str(segment.get("kind") or "")
    port = str(segment.get("port") or "")
    source_type = str(segment.get("source_type") or "")
    edge_id = str(segment.get("edge_id") or edge.get("id") or "").strip()
    if status != "active":
        return _reason_for_status(status, edge) or "Not included in this model input."
    if kind == "tool-schema":
        tool_name = str(metadata.get("display_name") or metadata.get("tool_name") or segment.get("label") or segment.get("prompt_id") or "this tool").strip()
        return (
            f"Tool schema exposed {tool_name} to the model as callable interface metadata. "
            "It can help the model request a tool call, but execution still requires tool policy, provider support, and authority approval."
        )
    if kind == "skill":
        return (
            "Runtime skill prompt matched the current message, selected skill, or tool metadata and was appended as system instructions for this response."
        )
    if kind == "memory":
        count = metadata.get("result_count")
        suffix = f" ({count} recalled item{'s' if count != 1 else ''})" if isinstance(count, int) and count > 0 else ""
        return f"Memory context was recalled for this conversation and inserted on the context port{suffix}."
    if kind == "context":
        if source_type == "api_route":
            return "Profile policy exposed this API route as policy context; it documents route availability and does not grant permissions by itself."
        count = metadata.get("result_count")
        suffix = f" ({count} result{'s' if count != 1 else ''})" if isinstance(count, int) and count > 0 else ""
        return f"Retrieved context matched the request and was inserted on the context port{suffix}."
    if port == "policy" or source_type == "profile_policy":
        return "Profile policy rules were connected to the policy port. They constrain behavior but do not originate from prompt text."
    if source_type == "profile_override":
        return "Profile override is the winning prompt source, so it replaced the snapshot/pack default in the model input."
    if source_type == "profile_snapshot":
        return "Profile snapshot supplied this prompt because no profile override was active."
    if source_type in {"pack", "pack_default"}:
        return "Pack default prompt was selected by the active profile and connected to the system prompt port."
    if source_type in {"extension", "canonical_fallback"}:
        return "Extension prompt was selected by the active profile and connected to the system prompt port."
    if edge_id:
        return f"Active AI Input Graph edge {edge_id} connected this segment to the {port or 'model'} input port."
    return "Selected by the active profile and included in the model input."


def _activation_detail(segment: dict[str, Any], metadata: dict[str, Any], edge: dict[str, Any]) -> dict[str, Any]:
    status = str(segment.get("status") or "available")
    kind = str(segment.get("kind") or "prompt")
    port = str(segment.get("port") or "")
    edge_id = str(segment.get("edge_id") or edge.get("id") or "")
    allow_disable = bool(segment.get("allow_disable", True))
    detail = {
        "state": status,
        "port": port,
        "edge_id": edge_id,
        "edge_kind": str(edge.get("kind") or ""),
        "effect": _input_role(kind, port),
        "control": "Can be toggled through AI Input Graph disabled_edges." if allow_disable else "Locked: allow_disable is false.",
        "reason": str(segment.get("reason") or ""),
    }
    if kind == "skill":
        detail["trigger"] = _skill_trigger_summary(metadata)
    elif kind == "tool-schema":
        detail["trigger"] = "Included because the tool is available to this profile/request and was not removed by the tool allowlist."
    elif kind in {"memory", "context"}:
        detail["trigger"] = str(metadata.get("source_kind") or segment.get("source") or "request context")
    else:
        detail["trigger"] = str(metadata.get("prompt_id") or metadata.get("resolved_prompt_id") or segment.get("prompt_id") or "profile selection")
    return detail


def _safety_boundary(kind: str) -> dict[str, Any]:
    summary = "Passive text only: cannot grant permissions, call tools, or mutate chat state."
    if kind == "tool-schema":
        summary = "Tool schema is interface metadata only; actual tool execution is checked by provider tool-calling, tool policy, and authority approval."
    elif kind == "skill":
        summary = "Skill prompt can add instructions for this response, but it cannot execute tools or bypass authority."
    return {
        "passive_text_only": True,
        "can_grant_permissions": False,
        "can_call_tools": False,
        "can_mutate_chat_state": False,
        "summary": summary,
    }


def _tool_signal(segment: dict[str, Any], raw_segment: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    kind = str(segment.get("kind") or "")
    if kind != "tool-schema":
        return {}
    tool_id = str(
        metadata.get("tool_id")
        or raw_segment.get("tool_id")
        or segment.get("prompt_id")
        or segment.get("id", "").removeprefix("tool_schema:")
        or ""
    ).strip()
    tool_name = str(metadata.get("tool_name") or raw_segment.get("name") or segment.get("label") or tool_id).strip()
    return {
        "tool_id": tool_id,
        "tool_name": tool_name,
        "display_name": str(metadata.get("display_name") or tool_name or tool_id),
        "provider_name": str(metadata.get("provider_name") or tool_name or tool_id),
        "source_pack_id": str(metadata.get("source_pack_id") or metadata.get("source") or ""),
        "available_to_model": str(segment.get("status") or "") == "active",
        "prompt_can_call_tool": False,
        "selection_source": "AI Input Graph tool schema segment",
        "execution_boundary": "The model may request this tool, then Rumi validates tool policy, provider support, local approval, and function/tool authority before any execution.",
        "skills": _list_strings(metadata.get("skills")),
        "skill_triggers": _list_strings(metadata.get("skill_triggers")),
    }


def _skill_signal(segment: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    kind = str(segment.get("kind") or "")
    if kind != "skill":
        return {}
    matched = metadata.get("matched_skills")
    matched_items = [dict(item) for item in matched if isinstance(item, dict)] if isinstance(matched, list) else []
    return {
        "matched": [
            {
                "id": str(item.get("id") or ""),
                "display_name": str(item.get("display_name") or item.get("id") or ""),
                "triggers": _list_strings(item.get("triggers")),
                "applies_to_tools": _list_strings(item.get("applies_to_tools")),
            }
            for item in matched_items
        ],
        "triggered_by": _skill_trigger_summary(metadata),
        "prompt_can_call_tool": False,
    }


def _skill_trigger_summary(metadata: dict[str, Any]) -> str:
    matched = metadata.get("matched_skills")
    if not isinstance(matched, list) or not matched:
        return "runtime skill selection"
    labels = []
    trigger_bits = []
    tool_bits = []
    for item in matched:
        if not isinstance(item, dict):
            continue
        label = str(item.get("display_name") or item.get("id") or "").strip()
        if label:
            labels.append(label)
        trigger_bits.extend(_list_strings(item.get("triggers")))
        tool_bits.extend(_list_strings(item.get("applies_to_tools")))
    parts = []
    if labels:
        parts.append("matched " + ", ".join(labels[:3]))
    if trigger_bits:
        parts.append("trigger words: " + ", ".join(dict.fromkeys(trigger_bits[:6])))
    if tool_bits:
        parts.append("tool scope: " + ", ".join(dict.fromkeys(tool_bits[:6])))
    return "; ".join(parts) if parts else "runtime skill selection"


def _input_role(kind: str, port: str) -> str:
    if kind == "tool-schema":
        return "tool schema exposed to the provider tools interface"
    if kind == "skill":
        return "runtime system instructions for this response"
    if kind == "memory":
        return "recalled memory inserted as context"
    if kind == "context":
        return "retrieved/context policy inserted into model context"
    if port == "policy":
        return "profile policy connected to the policy port"
    if port:
        return f"prompt text connected to the {port} port"
    return "prompt text connected to model input"


def _source_priority(source_type: str) -> str:
    if source_type == "profile_override":
        return "profile override wins over snapshots and pack defaults"
    if source_type == "profile_snapshot":
        return "profile snapshot wins over pack defaults unless an override exists"
    if source_type in {"pack", "pack_default"}:
        return "pack default is the fallback source"
    if source_type in {"extension", "canonical_fallback"}:
        return "extension-provided source"
    if source_type == "skill":
        return "runtime skill source, added after input-message matching"
    if source_type == "tool_schema":
        return "tool registry source, separate from prompt priority"
    return source_type or "runtime source"


def _list_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _is_editable(source_type: str, metadata: dict[str, Any]) -> bool:
    if source_type == "profile_override":
        return True
    if source_type in {"pack", "pack_default", "profile_snapshot", "component", "extension", "canonical_fallback"}:
        return False
    return not bool(metadata.get("read_only", False))


def _readonly_reason(source_type: str, metadata: dict[str, Any]) -> str:
    if _is_editable(source_type, metadata):
        return ""
    if source_type in {"pack", "pack_default"}:
        return "Pack prompts are read-only; create a profile override to edit."
    if source_type == "profile_snapshot":
        return "Profile snapshots are read-only; create a profile override to edit."
    if source_type == "component":
        return "Component prompts are read-only."
    if source_type in {"extension", "canonical_fallback"}:
        return "Extension prompts are read-only; create a profile override to edit."
    return "This segment is read-only in the current source."


def _reason_for_status(status: str, edge: dict[str, Any]) -> str:
    if status == "active":
        return "Connected to model input by the active AI Input Graph."
    if _edge_disabled_by_user(edge):
        return "Disabled by profile metadata.ai_input.disabled_edges."
    return ""


def _edge_disabled_by_user(edge: dict[str, Any]) -> bool:
    metadata = edge.get("metadata") if isinstance(edge.get("metadata"), dict) else {}
    return bool(metadata.get("disabled_by_ai_input"))


def _disabled_reason_label(reason: str, edge: dict[str, Any]) -> str:
    if reason == "budget_exceeded":
        return "Dropped by the prompt token budget."
    if _edge_disabled_by_user(edge):
        return "Disabled by the user through AI Input Graph disabled_edges."
    if reason == "policy_disabled":
        return "Disabled by profile policy."
    if reason == "edge_disabled_or_gate_blocked":
        return "Blocked by a disabled edge or gate."
    return reason or "Disabled before provider payload assembly."


def _source_counts(segments: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for segment in segments:
        key = str(segment.get("kind") or segment.get("source_type") or "prompt")
        counts[key] = counts.get(key, 0) + 1
    return counts
