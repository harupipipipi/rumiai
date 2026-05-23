from __future__ import annotations

import base64
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import gen_id
from domain.ai_client.capabilities.registry import get_model_provider_capabilities
from blocks.chat._context_helpers import enrich_messages, extract_user_text
from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
from domain.ai_client.model_router import ModelRoutingRequest, route_model_request
from domain.ai_client.model_search import get_model_capabilities
from domain.ai_client.request_planner import plan_model_request
from domain.chat.ir import RumiChatIR
from domain.chat.ir_blocks import IR_SCHEMA_VERSION
from domain.chat.ir_legacy_adapter import ir_to_legacy_standard_messages, stored_messages_to_ir
from domain.chat.modality_detector import detect_modalities
from domain.chat.store import ChatStore
from domain.vision.image_bridge import (
    apply_vision_bridge_to_messages,
    conversation_image_context,
    describe_images,
)
from domain.chat.tool_recommender import effective_tool_assist_mode, recommend_tool_ids, tool_assist_limit
from domain.prompt.manager import get_manager
from domain.skill_trigger import RuntimeSkillTriggerService
from domain.tool.registry import ToolRegistry
from domain.tool.schema_adapter import (
    adapt_tool_definitions,
    build_tool_execution_context,
    connected_tool_names,
    filter_tool_definitions_for_runtime_profile,
    resolve_runtime_profile_context,
    tool_name_from_definition,
)


MAX_ATTACHMENT_TEXT_CHARS = 240_000
MAX_ATTACHMENT_TEXT_CHARS_PER_FILE = 120_000
MAX_ATTACHMENT_IMAGE_BYTES = 8 * 1024 * 1024
_DATA_IMAGE_PREFIX = "data:image/"
_PROMPT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_COMPUTER_USE_REQUEST_RE = re.compile(
    r"compute[\s_-]*use|compu?ter[\s_-]*use|computer\s+ツール|コンピューター操作|pc操作|"
    r"(google\s*chrome|chrome|chatgpt|vivaldi|vivladi|line|ブラウザ|browser).{0,80}(操作|送信|入力|クリック|開いて|開く)",
    re.IGNORECASE,
)
_COMPUTER_USE_CHROME_TARGET_RE = re.compile(r"google\s*chrome|chrome|グーグル\s*クローム|クローム", re.IGNORECASE)
_COMPUTER_USE_CHROME_NEGATED_RE = re.compile(
    r"(google\s*chrome|chrome|グーグル\s*クローム|クローム).{0,16}"
    r"(使わない|使わず|禁止|not\s+use|do\s+not\s+use|don't\s+use)",
    re.IGNORECASE,
)
_COMPUTER_USE_VIVALDI_TARGET_RE = re.compile(r"vivaldi|vivladi|ヴィヴァルディ|ビバルディ", re.IGNORECASE)
_COMPUTER_USE_LINE_TARGET_RE = re.compile(r"(?<![A-Za-z])line(?![A-Za-z])|ライン", re.IGNORECASE)
_COMPUTER_USE_CHATGPT_TARGET_RE = re.compile(r"chat\s*gpt|chatgpt", re.IGNORECASE)


@dataclass
class PreparedChatRun:
    conversation_id: str
    conversation: dict[str, Any]
    input_data: dict[str, Any]
    request_id: str
    content: list[Any]
    metadata: dict[str, Any] | None
    user_message: dict[str, Any]
    model: str
    params: dict[str, Any]
    request_context: dict[str, Any]
    tool_context: dict[str, Any]
    standard_messages: list[dict[str, Any]]
    user_text: str
    system_prompt: str
    enrich_info: dict[str, Any]
    raw_tools: list[dict[str, Any]]
    provider_tools: list[dict[str, Any]]
    tools_called: list[str]
    connected_tool_names: set[str]
    call_handler: Any
    model_routing: dict[str, Any]
    chat_ir: RumiChatIR = field(default_factory=RumiChatIR)
    ir_schema_version: str = IR_SCHEMA_VERSION
    provider_planning: dict[str, Any] = field(default_factory=dict)
    provider_capabilities: dict[str, Any] = field(default_factory=dict)
    chat_references: dict[str, Any] = field(default_factory=dict)
    matched_skills: list[dict[str, Any]] = field(default_factory=list)


def validate_chat_run_input(input_data: dict[str, Any]) -> str | None:
    if not isinstance(input_data, dict):
        return "input_data dict is required"
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return "conversation_id is required"
    message = input_data.get("message")
    if not message or not isinstance(message, dict):
        return "message dict is required"
    raw_content = message.get("content")
    attachments = message.get("attachments")
    has_attachments = isinstance(attachments, list) and len(attachments) > 0
    if (raw_content is None or raw_content == "") and not has_attachments:
        return "message content must not be empty"
    if isinstance(raw_content, list) and len(raw_content) == 0 and not has_attachments:
        return "message content must not be empty"
    return None


def prepare_chat_run(input_data: dict[str, Any], context: dict[str, Any] | None = None) -> PreparedChatRun:
    store = ChatStore()
    conversation_id = str(input_data.get("conversation_id") or "")
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found")

    message = input_data.get("message") if isinstance(input_data.get("message"), dict) else {}
    content, metadata = _prepared_user_content(store, conversation_id, message)
    chat_references = _chat_references(store, conversation_id, metadata)
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata.setdefault("chat_references", chat_references)
    user_message = store.add_message(
        conversation_id,
        {
            "role": message.get("role", "user"),
            "content": content,
            "metadata": metadata or None,
        },
    )
    if user_message is None:
        raise RuntimeError("Failed to add user message")

    if _current_turn_history_only(context):
        message_chain = [user_message]
    else:
        message_chain = store.get_message_chain(conversation_id, user_message["id"])
    chat_ir = stored_messages_to_ir(conversation_id, message_chain)
    standard_messages = ir_to_legacy_standard_messages(chat_ir)
    runtime_content = _runtime_user_content_override(metadata)
    if runtime_content:
        _replace_current_user_content_for_model(
            standard_messages,
            role=str(user_message.get("role") or message.get("role") or "user"),
            runtime_content=runtime_content,
        )
    model = str((conversation or {}).get("model") or "stub/default")
    request_id = gen_id()

    manager = get_manager()
    system_prompt = _conversation_system_prompt(conversation, manager)
    user_text = extract_user_text(content)
    inferred_tool_ids = _infer_requested_tools_from_message(user_text)
    effective_inferred_tool_ids = [] if _has_explicit_selected_tools(input_data) else inferred_tool_ids
    prepared_input = _with_inferred_tools(input_data, effective_inferred_tool_ids)

    try:
        enrich_info = enrich_messages(standard_messages, system_prompt, conversation_id, user_text, manager)
    except Exception:
        enrich_info = {
            "knowledge_text": "",
            "memory_text": "",
            "knowledge_results": [],
            "memory_results": [],
            "enriched_prompt": system_prompt,
        }
        if system_prompt:
            standard_messages.insert(0, {"role": "system", "content": system_prompt})
    if system_prompt and (not standard_messages or standard_messages[0].get("role") != "system"):
        standard_messages.insert(0, {"role": "system", "content": system_prompt})
    chat_reference_prompt = _format_chat_references_for_prompt(chat_references)
    if chat_reference_prompt:
        insert_at = 1 if standard_messages and standard_messages[0].get("role") == "system" else 0
        standard_messages.insert(insert_at, {"role": "system", "content": chat_reference_prompt})

    params = dict(prepared_input.get("params") or {})
    requested_model = str(params.get("model") or params.get("profile_id") or "").strip()
    if requested_model:
        model = requested_model
    model_settings_service = ModelRuntimeSettingsService()
    model_settings = model_settings_service.get_settings()
    if "thinking_level" not in params:
        params["thinking_level"] = model_settings_service.get_effective_thinking_level(
            profile_id=model,
            conversation_id=conversation_id,
        )["level"]

    request_context = dict(context or {})
    if effective_inferred_tool_ids:
        request_context["user_requested_computer_use"] = True
        request_context = _apply_computer_use_context_preferences(request_context, user_text)
    request_context["conversation_id"] = conversation_id
    request_context["conversation_workspace_dir"] = str(store.conversation_workspace_dir(conversation_id))
    request_context["chat_references"] = chat_references
    request_context["history_json_path"] = chat_references["history_json_path"]
    request_context["model"] = model
    request_context["chat_params"] = params
    request_context["request_id"] = request_id
    request_context.update(_approval_followup_tool_context(metadata))
    tool_policy = params.get("tool_policy")
    if isinstance(tool_policy, dict):
        request_context["profile_policy"] = {
            **(request_context.get("profile_policy") if isinstance(request_context.get("profile_policy"), dict) else {}),
            **tool_policy,
        }
        tool_choice = tool_policy.get("tool_choice")
        if "tool_choice" not in params and (
            isinstance(tool_choice, dict)
            or str(tool_choice or "").strip().lower() in {"auto", "none", "required"}
        ):
            params["tool_choice"] = tool_choice

    raw_tools, provider_tools, tool_context = _available_tools(request_context, prepared_input, user_text=user_text)
    modalities = detect_modalities(content, metadata)
    routing_decision = route_model_request(
        ModelRoutingRequest(
            conversation_id=conversation_id,
            user_text=user_text,
            has_images=bool(modalities.get("has_images")),
            has_files=bool(modalities.get("has_files")),
            requested_tools=[tool_name_from_definition(tool) for tool in raw_tools if tool_name_from_definition(tool)],
            requires_tool_calling=bool(provider_tools),
            requested_thinking_level=params.get("thinking_level"),
            preferred_model=model,
            preferred_group=str(model_settings.get("preferred_model_group") or "default"),
            auto_route_within_group=bool(model_settings.get("auto_route_within_group", True)),
            task_hints={"modalities": modalities},
            settings=model_settings,
        )
    )
    model = routing_decision.selected_model
    selected_capabilities = get_model_capabilities(model) or {}
    provider_capabilities = get_model_provider_capabilities(
        model,
        {
            "id": model,
            "provider_id": model.split("/", 1)[0] if "/" in model else "",
            "capabilities": selected_capabilities,
            "metadata": {"capabilities": selected_capabilities},
            "supports_thinking": bool(selected_capabilities.get("supports_thinking")),
        },
    )
    if params.get("thinking_level") not in (None, "", "none") and not selected_capabilities.get("supports_thinking"):
        params["thinking_level"] = "none"
    if provider_tools and not selected_capabilities.get("supports_tool_calling") and not request_context.get("user_requested_computer_use"):
        unavailable_tools = [tool_name_from_definition(tool) for tool in raw_tools if tool_name_from_definition(tool)]
        tool_context["tool_suggestion_context"] = {
            "message": "Selected model does not support provider tool calling; tools were not attached.",
            "suggested_tools": unavailable_tools,
        }
        tool_context["tool_calling_unverified"] = True
        tool_context["tool_calling_unavailable_reason"] = "selected_model_does_not_support_tool_calling"
        tool_context["requested_tools_without_provider_attachment"] = unavailable_tools
        request_context["tool_calling_unverified"] = True
        request_context["tool_calling_unavailable_reason"] = "selected_model_does_not_support_tool_calling"
        request_context["requested_tools_without_provider_attachment"] = unavailable_tools
        provider_tools = []
    if routing_decision.bridge_required:
        bridge_result = describe_images(
            messages=standard_messages,
            attachments=(metadata or {}).get("attachments") if isinstance(metadata, dict) else [],
            conversation_context=user_text,
            model=routing_decision.bridge_plan.get("model", ""),
            call_handler=request_context.get("call_handler"),
        )
        standard_messages = apply_vision_bridge_to_messages(standard_messages, bridge_result)
        existing_metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
        store.update_conversation(
            conversation_id,
            {
                "metadata": {
                    **existing_metadata,
                    "conversation_image_context": conversation_image_context(bridge_result),
                }
            },
        )
        if isinstance(metadata, dict):
            metadata["vision_bridge_result"] = bridge_result
            store.update_message(conversation_id, user_message["id"], {"metadata": metadata})
    request_context["model"] = model
    request_context["chat_params"] = params
    request_context["model_routing"] = routing_decision.to_dict()
    connected_names = connected_tool_names(
        provider_tools,
        tool_context.get("runtime_profile") if isinstance(tool_context, dict) else None,
        agent_id=tool_context.get("agent_id") if isinstance(tool_context, dict) else None,
    )
    tool_context["chat_references"] = chat_references
    tool_context["history_json_path"] = chat_references["history_json_path"]
    skill_eval = RuntimeSkillTriggerService().evaluate(
        user_text=user_text,
        tool_names=[tool_name_from_definition(tool) for tool in raw_tools if tool_name_from_definition(tool)],
        context=request_context,
    )
    matched_skills = skill_eval.get("matched", []) if isinstance(skill_eval, dict) else []
    skill_instructions = str(skill_eval.get("instructions") or "").strip() if isinstance(skill_eval, dict) else ""
    if skill_instructions:
        insert_at = 1 if standard_messages and standard_messages[0].get("role") == "system" else 0
        standard_messages.insert(insert_at, {"role": "system", "content": skill_instructions})
        request_context["matched_skill_instructions"] = matched_skills
        tool_context["matched_skill_instructions"] = matched_skills

    planned_request = plan_model_request(
        chat_ir,
        model,
        provider_capabilities,
        provider_tools,
        params,
        request_context,
    )
    provider_planning = planned_request.to_dict()
    provider_tools = planned_request.provider_tools
    params = planned_request.params
    request_context["chat_params"] = params
    request_context["provider_capabilities"] = provider_capabilities
    request_context["provider_planning"] = provider_planning
    tool_context["provider_capabilities"] = provider_capabilities
    tool_context["provider_planning"] = provider_planning

    return PreparedChatRun(
        conversation_id=conversation_id,
        conversation=conversation,
        input_data=prepared_input,
        request_id=request_id,
        content=content,
        metadata=metadata,
        user_message=user_message,
        model=model,
        params=params,
        request_context=request_context,
        tool_context=tool_context,
        standard_messages=standard_messages,
        user_text=user_text,
        system_prompt=system_prompt,
        enrich_info=enrich_info,
        raw_tools=raw_tools,
        provider_tools=provider_tools,
        tools_called=[tool_name_from_definition(tool) for tool in raw_tools if tool_name_from_definition(tool)],
        connected_tool_names=connected_names,
        call_handler=request_context.get("call_handler"),
        model_routing=routing_decision.to_dict(),
        chat_ir=chat_ir,
        ir_schema_version=IR_SCHEMA_VERSION,
        provider_planning=provider_planning,
        provider_capabilities=provider_capabilities,
        chat_references=chat_references,
        matched_skills=matched_skills,
    )


def _current_turn_history_only(context: dict[str, Any] | None) -> bool:
    if not isinstance(context, dict):
        return False
    mode = str(
        context.get("chat_history_mode")
        or context.get("external_chat_history_mode")
        or context.get("history_mode")
        or ""
    ).strip().lower()
    return mode in {"current_turn", "current_message", "stateless", "none"}


def prefocus_computer_use_target_window(prepared: PreparedChatRun) -> Any:
    if not isinstance(prepared.request_context, dict) or not prepared.request_context.get("user_requested_computer_use"):
        return None
    target_app = str(prepared.request_context.get("computer_use_target_app") or "").strip()
    target_title = str(prepared.request_context.get("computer_use_target_title") or "").strip()
    if not (target_app or target_title):
        return None
    tool_name = next(
        (
            candidate
            for candidate in ("browser_computer", "computer_use", "browser_use")
            if candidate in prepared.connected_tool_names
        ),
        "",
    )
    if not tool_name:
        return None

    payload: dict[str, Any] = {}
    if target_app:
        payload["app"] = target_app
    if target_title:
        payload["title"] = target_title
    arguments = {"action": "computer.select_window", "payload": payload}
    invoke_context = build_tool_execution_context(prepared.tool_context, tool_name, prepared.connected_tool_names)
    if prepared.call_handler is not None:
        result = prepared.call_handler(
            "defaults.tool.invoke",
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "context": invoke_context,
            },
        )
        if isinstance(result, dict) and result.get("status") == "ok":
            return result.get("data", {})
        return result

    from domain.tool.executor import ToolExecutor

    return ToolExecutor().execute(tool_name, arguments, invoke_context)


def _prepared_user_content(store: ChatStore, conversation_id: str, message: dict[str, Any]) -> tuple[list[Any], dict[str, Any] | None]:
    content = message.get("content", [])
    attachments = message.get("attachments")
    has_attachments = isinstance(attachments, list) and len(attachments) > 0
    if (content is None or content == "" or content == []) and has_attachments:
        content = "添付ファイルを確認してください。"
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if isinstance(content, list):
        content = list(content)
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    if isinstance(attachments, list):
        metadata = dict(metadata)
        persisted_attachments = store.persist_attachments(conversation_id, attachments)
        metadata["attachments"] = _sanitize_attachment_metadata(attachments)
        if persisted_attachments:
            metadata["workspace_attachments"] = persisted_attachments
        if isinstance(content, list):
            content.extend(_attachment_text_blocks(attachments))
            content.extend(_attachment_image_blocks(attachments))
    return content if isinstance(content, list) else [{"type": "text", "text": str(content)}], metadata or None


def _chat_references(store: ChatStore, conversation_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    conversation_dir = store.conversation_dir(conversation_id)
    workspace_dir = store.conversation_workspace_dir(conversation_id)
    history_path = conversation_dir / "history.json"
    dropped_widgets = metadata.get("dropped_widgets") if isinstance(metadata, dict) and isinstance(metadata.get("dropped_widgets"), list) else []
    references = []
    for widget in dropped_widgets:
        if not isinstance(widget, dict):
            continue
        widget_meta = widget.get("metadata") if isinstance(widget.get("metadata"), dict) else {}
        ref_id = str(widget_meta.get("conversation_id") or widget.get("sourceItemId") or "").strip()
        if not ref_id or ref_id == conversation_id:
            continue
        ref_conv = store.get_conversation(ref_id) or {}
        ref_dir = store.conversation_dir(ref_id)
        references.append(
            {
                "conversation_id": ref_id,
                "title": str(widget_meta.get("title") or ref_conv.get("title") or widget.get("label") or ref_id),
                "summary": _summarize_referenced_conversation(ref_conv),
                "history_json_path": str(ref_dir / "history.json"),
            }
        )
    return {
        "conversation_id": conversation_id,
        "conversation_dir": str(conversation_dir),
        "workspace_dir": str(workspace_dir),
        "history_json_path": str(history_path),
        "history_path": str(history_path),
        "references": references,
    }


def _format_chat_references_for_prompt(chat_references: dict[str, Any]) -> str:
    refs = chat_references.get("references") if isinstance(chat_references, dict) else []
    if not isinstance(refs, list) or not refs:
        return ""
    lines = ["--- Dropped Chat References ---"]
    for index, ref in enumerate(refs, 1):
        if not isinstance(ref, dict):
            continue
        lines.append(
            "[{}] chat_id={} title={} history_json={}\nsummary: {}".format(
                index,
                ref.get("conversation_id") or "",
                ref.get("title") or "",
                ref.get("history_json_path") or "",
                ref.get("summary") or "",
            )
        )
    return "\n".join(lines).strip()


def _summarize_referenced_conversation(conversation: dict[str, Any]) -> str:
    messages = conversation.get("messages") if isinstance(conversation, dict) and isinstance(conversation.get("messages"), list) else []
    snippets = []
    for message in messages[-8:]:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "message")
        text = _content_text(message.get("content"))
        if text:
            snippets.append(f"{role}: {text[:240]}")
    return "\n".join(snippets)[-1600:]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif block.get("type") in {"image", "image_url"}:
                parts.append("[image]")
            elif block.get("type"):
                parts.append(f"[{block.get('type')}]")
    return " ".join(part.strip() for part in parts if str(part).strip())


def _runtime_user_content_override(metadata: dict[str, Any] | None) -> str:
    if not isinstance(metadata, dict):
        return ""
    external = metadata.get("external") if isinstance(metadata.get("external"), dict) else {}
    value = external.get("runtime_content") or metadata.get("runtime_content")
    if not isinstance(value, str):
        return ""
    return value.strip()


def _approval_followup_tool_context(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    followup = metadata.get("approval_followup")
    if not isinstance(followup, dict):
        return {}
    token = str(followup.get("approval_token") or followup.get("token") or "").strip()
    tool_name = str(followup.get("tool_name") or "").strip()
    if not token or not tool_name:
        return {}
    operation = str(followup.get("operation") or followup.get("action") or "").strip()
    request_id = str(followup.get("request_id") or followup.get("approval_request_id") or "").strip()
    token_map = {tool_name: token}
    if operation:
        token_map[operation] = token
    if request_id:
        token_map[request_id] = token
    return {"tool_approval_tokens": token_map}


def _replace_current_user_content_for_model(
    standard_messages: list[dict[str, Any]],
    *,
    role: str,
    runtime_content: str,
) -> None:
    if not runtime_content:
        return
    target_role = str(role or "user").strip() or "user"
    for message in reversed(standard_messages):
        if isinstance(message, dict) and str(message.get("role") or "user") == target_role:
            message["content"] = runtime_content
            return


def _conversation_system_prompt(conv: dict[str, Any], manager: Any) -> str:
    prompt_id = str((conv or {}).get("system_prompt_id") or "").strip()
    if not prompt_id:
        return manager.get_system_prompt()
    prompt = manager.get_prompt(prompt_id) or manager.get_prompt_by_name(prompt_id)
    if isinstance(prompt, dict):
        body = prompt.get("body") or prompt.get("content")
        if body:
            return str(body)
    if _PROMPT_ID_RE.match(prompt_id):
        prompt_path = Path(__file__).resolve().parents[2] / "prompts" / (prompt_id + ".system.md")
        try:
            if prompt_path.is_file():
                return prompt_path.read_text(encoding="utf-8")
        except OSError:
            pass
    return manager.get_system_prompt()


def _attachment_text_blocks(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = []
    remaining = MAX_ATTACHMENT_TEXT_CHARS
    for attachment in attachments:
        if remaining <= 0 or not isinstance(attachment, dict):
            break
        text = attachment.get("content")
        if not isinstance(text, str) or not text:
            continue
        limit = min(MAX_ATTACHMENT_TEXT_CHARS_PER_FILE, remaining)
        clipped = text[:limit]
        was_truncated = len(text) > limit or attachment.get("truncated") is True
        remaining -= len(clipped)
        name = str(attachment.get("name") or "unnamed").strip()[:200] or "unnamed"
        suffix = "\n..." if was_truncated else ""
        blocks.append(
            {
                "type": "text",
                "text": "\n\n添付ファイル: {}\n```\n{}{}\n```".format(name, clipped, suffix),
            }
        )
    return blocks


def _attachment_image_blocks(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        mime = str(attachment.get("type") or "").lower()
        data_url = attachment.get("dataUrl") or attachment.get("data_url")
        byte_length = _image_data_url_byte_length(data_url)
        if not mime.startswith("image/") or byte_length is None:
            continue
        size = attachment.get("size")
        if isinstance(size, int) and size > MAX_ATTACHMENT_IMAGE_BYTES:
            continue
        if byte_length > MAX_ATTACHMENT_IMAGE_BYTES:
            continue
        blocks.append({"type": "image_url", "image_url": {"url": data_url}})
    return blocks


def _sanitize_attachment_metadata(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        sanitized.append(
            {
                key: attachment.get(key)
                for key in ("id", "name", "size", "type", "truncated", "source", "sourcePath")
                if key in attachment
            }
        )
    return sanitized


def _image_data_url_byte_length(data_url: Any) -> int | None:
    if not isinstance(data_url, str) or not data_url.startswith(_DATA_IMAGE_PREFIX):
        return None
    header, separator, encoded = data_url.partition(",")
    if not separator or ";base64" not in header.lower():
        return None
    try:
        return len(base64.b64decode(encoded, validate=True))
    except Exception:
        return None


def _resolve_selected_tools(
    raw_tools: Any,
    *,
    user_text: str = "",
    context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    registry = ToolRegistry()
    if not isinstance(raw_tools, list):
        tools = registry.list_tools()
        mode = effective_tool_assist_mode(pack_root=Path(__file__).resolve().parents[2])
        if mode == "off":
            return [], []
        if mode == "all":
            return tools, []
        recommended_ids = recommend_tool_ids(
            user_text,
            tools,
            limit=tool_assist_limit(pack_root=Path(__file__).resolve().parents[2]),
        )
        resolved = [tool for tool in tools if str(tool.get("tool_id") or "") in set(recommended_ids)]
        if isinstance(context, dict):
            context["tool_assist"] = {
                "mode": "vector",
                "recommended_tools": recommended_ids,
                "available_tool_count": len(tools),
            }
        return resolved, []
    resolved = []
    unknown = []
    for item in raw_tools:
        if isinstance(item, dict):
            resolved.append(item)
            continue
        if not isinstance(item, str):
            continue
        tool_id = item.strip()
        if not tool_id:
            continue
        tool_def = registry.get(tool_id)
        if tool_def is None:
            unknown.append(tool_id)
            continue
        resolved.append(tool_def)
    return resolved, unknown


def _infer_requested_tools_from_message(user_text: str) -> list[str]:
    if not isinstance(user_text, str) or not _COMPUTER_USE_REQUEST_RE.search(user_text):
        return []
    return ["computer_use", "browser_computer"]


def _with_inferred_tools(input_data: dict[str, Any], inferred_tool_ids: list[str]) -> dict[str, Any]:
    if not inferred_tool_ids:
        return input_data
    if _has_explicit_selected_tools(input_data):
        return input_data
    raw_tools = input_data.get("tools")
    existing_tools = list(raw_tools) if isinstance(raw_tools, list) else []
    merged = []
    seen = set()
    for item in existing_tools + list(inferred_tool_ids):
        key = item if isinstance(item, str) else id(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    updated = dict(input_data)
    updated["tools"] = merged
    return updated


def _has_explicit_selected_tools(input_data: dict[str, Any]) -> bool:
    params = input_data.get("params") if isinstance(input_data.get("params"), dict) else {}
    tool_policy = params.get("tool_policy") if isinstance(params.get("tool_policy"), dict) else {}
    if "selected_tools" in tool_policy:
        return True
    message = input_data.get("message") if isinstance(input_data.get("message"), dict) else {}
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    return "selected_tools" in metadata


def _computer_use_preferences_from_text(user_text: str) -> dict[str, Any]:
    text = user_text if isinstance(user_text, str) else ""
    preferences = {}
    if _COMPUTER_USE_VIVALDI_TARGET_RE.search(text):
        preferences["computer_use_target_app"] = "Vivaldi"
    elif _COMPUTER_USE_CHROME_TARGET_RE.search(text) and not _COMPUTER_USE_CHROME_NEGATED_RE.search(text):
        preferences["computer_use_target_app"] = "Google Chrome"
    if _COMPUTER_USE_LINE_TARGET_RE.search(text):
        preferences["computer_use_target_title"] = "LINE"
    elif _COMPUTER_USE_CHATGPT_TARGET_RE.search(text):
        preferences["computer_use_target_title"] = "ChatGPT"
    return preferences


def _apply_computer_use_context_preferences(context: dict[str, Any], user_text: str) -> dict[str, Any]:
    updated = dict(context or {})
    preferences = _computer_use_preferences_from_text(user_text)
    for key, value in preferences.items():
        if value not in (None, "", False):
            updated[key] = value
    return updated


def _available_tools(
    context: dict[str, Any],
    input_data: dict[str, Any],
    *,
    user_text: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    raw_tools = input_data.get("tools")
    params = input_data.get("params") if isinstance(input_data.get("params"), dict) else {}
    tool_policy = params.get("tool_policy") if isinstance(params.get("tool_policy"), dict) else {}
    if raw_tools is None and isinstance(tool_policy, dict) and "selected_tools" in tool_policy:
        raw_tools = tool_policy.get("selected_tools")
    if raw_tools is None:
        message = input_data.get("message") if isinstance(input_data.get("message"), dict) else {}
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        if "selected_tools" in metadata:
            raw_tools = metadata.get("selected_tools")
    try:
        tools, unknown_tools = _resolve_selected_tools(raw_tools, user_text=user_text, context=context)
    except Exception:
        tools, unknown_tools = [], []
    resolved_context = resolve_runtime_profile_context(context or {})
    if unknown_tools:
        resolved_context["unknown_selected_tools"] = unknown_tools
    runtime_profile = resolved_context.get("runtime_profile")
    agent_id = input_data.get("agent_id")
    filtered = filter_tool_definitions_for_runtime_profile(
        tools,
        runtime_profile,
        agent_id=agent_id,
        policy_context=resolved_context,
    )
    return filtered, adapt_tool_definitions(filtered), resolved_context
