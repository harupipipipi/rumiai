from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import gen_id
from blocks.chat._context_helpers import enrich_messages, extract_user_text
from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
from domain.ai_client.model_router import ModelRoutingRequest, route_model_request
from domain.ai_client.model_search import get_model_capabilities
from domain.chat.message_converter import convert_to_standard
from domain.chat.modality_detector import detect_modalities
from domain.chat.store import ChatStore
from domain.chat.tool_selection_schema import COMPUTER_TOOL_IDS
from domain.vision.image_bridge import (
    apply_vision_bridge_to_messages,
    conversation_image_context,
    describe_images,
)
from domain.chat.tool_recommender import effective_tool_assist_mode, recommend_tool_ids, tool_assist_limit
from domain.prompt.manager import get_manager
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

    standard_messages = convert_to_standard(store.get_message_chain(conversation_id, user_message["id"]))
    model = str((conversation or {}).get("model") or "stub/default")
    request_id = gen_id()

    manager = get_manager()
    system_prompt = _conversation_system_prompt(conversation, manager)
    user_text = extract_user_text(content)
    inferred_tool_ids = _infer_requested_tools_from_message(user_text)
    prepared_input = _with_inferred_tools(input_data, inferred_tool_ids)

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

    params = dict(prepared_input.get("params") or {})
    model_settings_service = ModelRuntimeSettingsService()
    model_settings = model_settings_service.get_settings()
    if "thinking_level" not in params:
        params["thinking_level"] = model_settings_service.get_effective_thinking_level(
            profile_id=model,
            conversation_id=conversation_id,
        )["level"]

    request_context = dict(context or {})
    if inferred_tool_ids:
        request_context["user_requested_computer_use"] = True
        request_context = _apply_computer_use_context_preferences(request_context, user_text)
    request_context["conversation_id"] = conversation_id
    request_context["conversation_workspace_dir"] = str(store.conversation_workspace_dir(conversation_id))
    request_context["model"] = model
    request_context["chat_params"] = params
    request_context["request_id"] = request_id
    tool_policy = params.get("tool_policy")
    if isinstance(tool_policy, dict):
        request_context["profile_policy"] = {
            **(request_context.get("profile_policy") if isinstance(request_context.get("profile_policy"), dict) else {}),
            **tool_policy,
        }

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
    if params.get("thinking_level") not in (None, "", "none") and not selected_capabilities.get("supports_thinking"):
        params["thinking_level"] = "none"
    if provider_tools and not selected_capabilities.get("supports_tool_calling") and not request_context.get("user_requested_computer_use"):
        tool_context["tool_suggestion_context"] = {
            "message": "Selected model does not support provider tool calling; tools were not attached.",
            "suggested_tools": [tool_name_from_definition(tool) for tool in raw_tools if tool_name_from_definition(tool)],
        }
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
    )


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
                "mode": "auto",
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
    try:
        tools, unknown_tools = _resolve_selected_tools(raw_tools, user_text=user_text, context=context)
    except Exception:
        tools, unknown_tools = [], []
    resolved_context = resolve_runtime_profile_context(context or {})
    if unknown_tools:
        resolved_context["unknown_selected_tools"] = unknown_tools
    runtime_profile = resolved_context.get("runtime_profile")
    agent_id = input_data.get("agent_id")
    filtered = filter_tool_definitions_for_runtime_profile(tools, runtime_profile, agent_id=agent_id)
    return filtered, adapt_tool_definitions(filtered), resolved_context
