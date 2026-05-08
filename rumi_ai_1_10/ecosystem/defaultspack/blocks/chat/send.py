import sys
import os
import json
import re
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.ai_client.client import AIClient
from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService
from domain.chat.store import ChatStore
from domain.chat.message_converter import convert_to_standard
from domain.chat.message_builder import build_assistant_message
from domain.dev.inspector import Inspector
from domain.prompt.manager import get_manager
from blocks.chat._context_helpers import extract_user_text, enrich_messages
from domain.tool.registry import ToolRegistry
from domain.tool.schema_adapter import (
    adapt_tool_definitions,
    build_tool_execution_context,
    connected_tool_names,
    filter_tool_definitions_for_runtime_profile,
    max_tool_calls,
    resolve_runtime_profile_context,
    tool_name_from_definition,
)


MAX_ATTACHMENT_TEXT_CHARS = 240_000
MAX_ATTACHMENT_TEXT_CHARS_PER_FILE = 120_000
MAX_ATTACHMENT_IMAGE_BYTES = 8 * 1024 * 1024
_DATA_IMAGE_PREFIX = "data:image/"
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|credential|password|secret|token)",
    re.IGNORECASE,
)
_PROMPT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_COMPUTER_USE_REQUEST_RE = re.compile(
    r"compute[\s_-]*use|compu?ter[\s_-]*use|computer\s+ツール|コンピューター操作|pc操作|"
    r"(vivaldi|vivladi|line|ブラウザ|browser).{0,24}(操作|送信|入力|クリック|開いて|開く)",
    re.IGNORECASE,
)


def _stub_response():
    return {
        "content": [{"type": "text", "text": "[stub] AI response placeholder"}],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _conversation_system_prompt(conv, manager):
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


def _has_real_provider(client, model):
    """model に対応する実プロバイダーが登録されているか判定する。
    stub プロバイダーに解決される場合は False を返す。
    ただし model が 'stub/' で始まる場合は意図的な stub 利用とみなし True を返す。"""
    if model.startswith("stub/"):
        return True
    provider, _ = client.resolve_provider(model)
    from domain.ai_client.providers.stub_provider import StubProvider
    return not isinstance(provider, StubProvider)


def _ai_direct_complete(model, messages, tools=None, params=None):
    """AIClient を直接呼び出して complete を実行する。
    APIキー未設定等で実プロバイダーがない場合は明示的エラーを返す。

    Returns:
        (response_dict, None) on success
        (None, error_message) on failure
    """
    try:
        client = AIClient()
        if not _has_real_provider(client, model):
            return None, "AI provider API key not configured"
        response = client.complete(model, messages, tools or [], params or {})
        return response, None
    except RuntimeError as exc:
        return None, "AI request failed: " + str(exc)


def _event(event_type, message, **extra):
    payload = {
        "type": event_type,
        "message": message,
        "timestamp": timestamp(),
    }
    payload.update(_redact_sensitive_value(extra))
    return payload


def _redact_sensitive_value(value, *, parent_key=""):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_sensitive_value(item, parent_key=key_text)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_value(item, parent_key=parent_key) for item in value]
    if isinstance(value, str):
        if parent_key and _SECRET_KEY_RE.search(parent_key):
            return "[redacted]"
        if value.startswith("data:image/"):
            return "[image data saved as artifact]"
    return value


def _resolve_selected_tools(raw_tools):
    registry = ToolRegistry()
    if not isinstance(raw_tools, list):
        return registry.list_tools(), []

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


def _infer_requested_tools_from_message(user_text):
    if not isinstance(user_text, str) or not _COMPUTER_USE_REQUEST_RE.search(user_text):
        return []
    return ["computer_use", "browser_computer"]


def _with_inferred_tools(input_data, inferred_tool_ids):
    if not inferred_tool_ids or not isinstance(input_data.get("tools"), list):
        return input_data
    merged = []
    seen = set()
    for item in list(input_data.get("tools") or []) + list(inferred_tool_ids):
        key = item if isinstance(item, str) else id(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    updated = dict(input_data)
    updated["tools"] = merged
    return updated


def _available_tools(context, input_data):
    raw_tools = input_data.get("tools")
    try:
        tools, unknown_tools = _resolve_selected_tools(raw_tools)
    except Exception:
        tools, unknown_tools = [], []
    resolved_context = resolve_runtime_profile_context(context or {})
    if unknown_tools:
        resolved_context["unknown_selected_tools"] = unknown_tools
    runtime_profile = resolved_context.get("runtime_profile")
    agent_id = input_data.get("agent_id")
    filtered = filter_tool_definitions_for_runtime_profile(tools, runtime_profile, agent_id=agent_id)
    return filtered, adapt_tool_definitions(filtered), resolved_context


def _tool_use_blocks(response):
    blocks = response.get("content", []) if isinstance(response, dict) else []
    if not isinstance(blocks, list):
        return []
    return [
        block
        for block in blocks
        if isinstance(block, dict) and block.get("type") in {"tool_use", "tool_call"}
    ]


def _response_text(response):
    blocks = response.get("content", []) if isinstance(response, dict) else []
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ""
    parts = []
    for block in blocks:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts)


def _params_without_thinking(params):
    retry_params = dict(params or {})
    for key in ("thinking", "thinking_level", "reasoning_effort"):
        retry_params.pop(key, None)
    return retry_params


def _empty_response_message(finish_reason):
    reason = str(finish_reason or "unknown").strip() or "unknown"
    return (
        "モデルから本文のない応答が返りました。"
        "もう一度送信するか、thinkingを「なし」にして試してください。"
        f" (finish_reason: {reason})"
    )


def _tool_arguments(block):
    value = block.get("input", block.get("arguments", {}))
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"value": value}
    return value if isinstance(value, dict) else {}


def _append_assistant_tool_use_message(messages, tool_uses):
    tool_calls = []
    for block in tool_uses:
        tool_name = str(block.get("name") or block.get("tool_name") or "")
        if not tool_name:
            continue
        tool_call_id = str(block.get("id") or block.get("tool_call_id") or gen_id())
        arguments = _tool_arguments(block)
        tool_calls.append(
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        )
    if not tool_calls:
        return
    messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
        }
    )


def _model_supports_vision(model):
    try:
        client = AIClient()
        matches = client._runtime_model_matches(str(model or ""))
    except Exception:
        matches = []
    for match in matches or []:
        capabilities = match.get("capabilities", [])
        if isinstance(capabilities, dict):
            if capabilities.get("vision") or capabilities.get("image_input") or capabilities.get("multimodal"):
                return True
        elif any(str(item) in {"vision", "image_input", "multimodal"} for item in capabilities or []):
            return True
    return any(token in str(model or "").lower() for token in ("gemini", "gemma", "gpt-4o", "gpt-5"))


def _model_supports_attachments(model):
    try:
        client = AIClient()
        matches = client._runtime_model_matches(str(model or ""))
    except Exception:
        matches = []
    for match in matches or []:
        for source in (
            match,
            match.get("metadata", {}) if isinstance(match, dict) else {},
            match.get("availability", {}) if isinstance(match, dict) else {},
        ):
            if isinstance(source, dict) and source.get("supports_attachments") is False:
                return False
    return True


def _image_data_url_byte_length(data_url):
    if not isinstance(data_url, str) or not data_url.startswith(_DATA_IMAGE_PREFIX):
        return None
    header, separator, encoded = data_url.partition(",")
    if not separator or ";base64" not in header.lower():
        return None
    try:
        import base64

        return len(base64.b64decode(encoded, validate=True))
    except Exception:
        return None


def _browser_screenshot_data_url(result):
    if not isinstance(result, dict):
        return ""
    data = result.get("data", result)
    if not isinstance(data, dict):
        return ""
    widget = data.get("widget") if isinstance(data.get("widget"), dict) else {}
    candidates = [data, widget]
    for candidate in candidates:
        data_url = candidate.get("data_url") or candidate.get("dataUrl")
        byte_length = _image_data_url_byte_length(data_url)
        if byte_length is not None and byte_length <= MAX_ATTACHMENT_IMAGE_BYTES:
            return data_url
    path = data.get("path") or widget.get("path")
    mime = data.get("mime_type") or widget.get("mime_type") or "image/png"
    if isinstance(path, str) and path:
        try:
            import base64

            encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
            return "data:{};base64,{}".format(mime, encoded)
        except Exception:
            return ""
    return ""


def _browser_screenshot_guidance(result):
    if not isinstance(result, dict):
        return "Browser screenshot captured by browser_computer. Use this image to continue the task."
    data = result.get("data", result)
    if not isinstance(data, dict):
        return "Browser screenshot captured by browser_computer. Use this image to continue the task."
    widget = data.get("widget") if isinstance(data.get("widget"), dict) else {}
    source = widget if widget.get("coordinate_system") else data
    image_size = source.get("image_size") if isinstance(source.get("image_size"), dict) else {}
    action_coordinate_system = source.get("action_coordinate_system") if isinstance(source.get("action_coordinate_system"), dict) else {}
    model_image_size = source.get("model_image_size") if isinstance(source.get("model_image_size"), dict) else {}
    scale = source.get("model_to_action_scale") if isinstance(source.get("model_to_action_scale"), dict) else {}
    cursor = source.get("cursor") if isinstance(source.get("cursor"), dict) else {}
    parts = ["Browser screenshot captured by browser_computer. Use this image to continue the task."]
    if image_size.get("width") and image_size.get("height"):
        parts.append(
            "The attached screenshot image is top-left pixel space: width={} height={}.".format(
                image_size.get("width"),
                image_size.get("height"),
            )
        )
    if action_coordinate_system.get("width") and action_coordinate_system.get("height"):
        parts.append(
            "Mouse actions use top-left action coordinates: width={} height={} x_range={} y_range={}.".format(
                action_coordinate_system.get("width"),
                action_coordinate_system.get("height"),
                action_coordinate_system.get("x_range"),
                action_coordinate_system.get("y_range"),
            )
        )
    if model_image_size.get("width") and model_image_size.get("height") and scale.get("x") and scale.get("y"):
        parts.append(
            "If you estimate a point on the attached image, convert it to action coordinates with scale x={:.4f}, y={:.4f} before moving.".format(
                float(scale.get("x")),
                float(scale.get("y")),
            )
        )
    if cursor.get("x") is not None and cursor.get("y") is not None:
        parts.append("Current cursor is near x={} y={}.".format(cursor.get("x"), cursor.get("y")))
    parts.append("To reposition without clicking, call browser_use with action=move and integer x/y action coordinates.")
    return " ".join(parts)


def _append_tool_result_message(messages, tool_name, result, tool_call_id="", *, model=""):
    result_text = ""
    if isinstance(result, dict):
        data = result.get("data", result)
        if isinstance(data, dict):
            result_text = str(data.get("result", data.get("summary", json.dumps(data, ensure_ascii=False))))
        else:
            result_text = str(data)
    else:
        result_text = str(result)
    messages.append(
        {
            "role": "tool",
            "name": tool_name,
            "tool_call_id": tool_call_id,
            "content": result_text,
        }
    )
    if (
        tool_name in {"browser_computer", "browser_use", "computer_use"}
        and _model_supports_vision(model)
        and _model_supports_attachments(model)
    ):
        screenshot = _browser_screenshot_data_url(result)
        if screenshot:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": _browser_screenshot_guidance(result),
                        },
                        {"type": "image_url", "image_url": {"url": screenshot}},
                    ],
                }
            )


def _compact_tool_log_value(value):
    value = _redact_sensitive_value(value)
    if isinstance(value, dict):
        compact = {}
        for key, item in value.items():
            if key in {"data_url", "dataUrl"} and isinstance(item, str) and item.startswith("data:image/"):
                compact[key] = "[image data saved as artifact]"
            else:
                compact[key] = _compact_tool_log_value(item)
        return compact
    if isinstance(value, list):
        return [_compact_tool_log_value(item) for item in value]
    if isinstance(value, str) and "data:image/" in value:
        import re

        return re.sub(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+", "[image data saved as artifact]", value)
    return value


def _tool_visibility_message(tools):
    names = []
    for tool in tools or []:
        name = tool_name_from_definition(tool)
        if not name:
            continue
        description = ""
        if isinstance(tool, dict):
            function_def = tool.get("function")
            if isinstance(function_def, dict):
                description = str(function_def.get("description") or "")
            description = description or str(tool.get("description") or tool.get("summary") or "")
        label = name if not description else "{}: {}".format(name, description)
        names.append(label)
    if not names:
        return None
    return {
        "role": "system",
        "content": (
            "Available tools are connected for this turn. "
            "Use them when they are relevant, and do not claim that no tools are available. "
            "Connected tools: " + "; ".join(names)
        ),
    }


def _complete_with_tools(model, messages, tools, context, call_handler, params):
    events = [_event("status", "{} が考えています".format(model), phase="thinking", model=model)]
    tool_logs = []
    if tools:
        events.append(
            _event(
                "status",
                "{} 個の tool を接続しました".format(len(tools)),
                phase="tools_attached",
                tool_count=len(tools),
            )
        )

    working_messages = list(messages)
    tool_context_message = _tool_visibility_message(tools)
    if tool_context_message is not None:
        insert_at = 1 if working_messages and working_messages[0].get("role") == "system" else 0
        working_messages.insert(insert_at, tool_context_message)
    response = None
    limit = max_tool_calls(context or {})
    if limit is None:
        limit = int(params.get("max_tool_calls", 4) or 4)
    connected_names = connected_tool_names(tools, context.get("runtime_profile") if isinstance(context, dict) else None)

    for step_index in range(max(1, limit + 1)):
        ai_params = {
            "model": model,
            "messages": working_messages,
            "tools": tools,
            "params": params,
        }
        if call_handler is not None:
            response = call_handler("defaults.ai.complete", ai_params)
            if isinstance(response, dict) and response.get("status") == "error":
                err = response.get("error", {})
                raise RuntimeError(str(err.get("message") or "AI request failed"))
            if isinstance(response, dict) and response.get("status") == "ok":
                response = response.get("data", {})
        else:
            response, ai_error = _ai_direct_complete(model, working_messages, tools, params)
            if ai_error is not None:
                raise RuntimeError(ai_error)

        if not isinstance(response, dict):
            response = _stub_response()
        tool_uses = _tool_use_blocks(response)
        if not tool_uses and not _response_text(response).strip():
            retry_params = _params_without_thinking(params)
            if retry_params != params:
                retry_response = None
                if call_handler is not None:
                    retry_payload = {
                        "model": model,
                        "messages": working_messages,
                        "tools": tools,
                        "params": retry_params,
                    }
                    retry_response = call_handler("defaults.ai.complete", retry_payload)
                    if isinstance(retry_response, dict) and retry_response.get("status") == "ok":
                        retry_response = retry_response.get("data", {})
                else:
                    retry_response, ai_error = _ai_direct_complete(
                        model,
                        working_messages,
                        tools,
                        retry_params,
                    )
                    if ai_error is not None:
                        retry_response = None
                if isinstance(retry_response, dict) and (
                    _response_text(retry_response).strip() or _tool_use_blocks(retry_response)
                ):
                    retry_metadata = dict(retry_response.get("metadata") or {})
                    retry_metadata["recovered_from_empty_response"] = True
                    retry_response["metadata"] = retry_metadata
                    response = retry_response
                    tool_uses = _tool_use_blocks(response)
        if not tool_uses or step_index >= limit:
            break

        _append_assistant_tool_use_message(working_messages, tool_uses)
        for block in tool_uses:
            tool_name = str(block.get("name") or block.get("tool_name") or "")
            if not tool_name:
                continue
            tool_call_id = str(block.get("id") or block.get("tool_call_id") or gen_id())
            arguments = _tool_arguments(block)
            events.append(
                _event(
                    "tool_call_started",
                    "{} を使用中".format(tool_name),
                    phase="tool_call_started",
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    arguments=arguments,
                )
            )
            invoke_context = build_tool_execution_context(context or {}, tool_name, connected_names)
            if call_handler is not None:
                result = call_handler(
                    "defaults.tool.invoke",
                    {
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "context": invoke_context,
                    },
                )
            else:
                from domain.tool.executor import ToolExecutor

                executed = ToolExecutor().execute(tool_name, arguments, invoke_context)
                result = {"status": "ok", "data": executed}
            log = {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": _redact_sensitive_value(arguments),
                "result": _compact_tool_log_value(result),
                "timestamp": timestamp(),
            }
            tool_logs.append(log)
            events.append(
                _event(
                    "tool_call_completed",
                    "{} の結果を受け取りました".format(tool_name),
                    phase="tool_call_completed",
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    is_error=isinstance(result, dict) and result.get("status") == "error",
                )
            )
            _append_tool_result_message(
                working_messages,
                tool_name,
                result,
                tool_call_id,
                model=model,
            )

    response = response or _stub_response()
    if not _tool_use_blocks(response) and not _response_text(response).strip():
        content = response.get("content")
        if not isinstance(content, list):
            content = []
        response["content"] = [{"type": "text", "text": _empty_response_message(response.get("finish_reason"))}]
        metadata = dict(response.get("metadata") or {})
        metadata["empty_ai_response"] = True
        response["metadata"] = metadata
    existing_events = response.get("events", [])
    response["events"] = events + (existing_events if isinstance(existing_events, list) else [])
    response["tool_logs"] = tool_logs
    metadata = dict(response.get("metadata", {}))
    metadata.update(
        {
            "model": model,
            "attached_tool_count": len(tools),
            "attached_tools": [tool_name_from_definition(tool) for tool in tools if tool_name_from_definition(tool)],
            "thinking": {"state": "completed"},
            "thinking_level": params.get("thinking_level"),
        }
    )
    response["metadata"] = metadata
    return response


def _attachment_text_blocks(attachments):
    if not isinstance(attachments, list):
        return []

    blocks = []
    remaining = MAX_ATTACHMENT_TEXT_CHARS
    for attachment in attachments:
        if remaining <= 0:
            break
        if not isinstance(attachment, dict):
            continue
        text = attachment.get("content")
        if not isinstance(text, str) or not text:
            continue

        limit = min(MAX_ATTACHMENT_TEXT_CHARS_PER_FILE, remaining)
        clipped = text[:limit]
        was_truncated = len(text) > limit or attachment.get("truncated") is True
        remaining -= len(clipped)

        name = attachment.get("name")
        if not isinstance(name, str) or not name.strip():
            name = "unnamed"
        name = name.strip()[:200]

        suffix = "\n..." if was_truncated else ""
        blocks.append(
            {
                "type": "text",
                "text": "\n\n添付ファイル: {}\n```\n{}{}\n```".format(name, clipped, suffix),
            }
        )
    return blocks


def _attachment_image_blocks(attachments):
    if not isinstance(attachments, list):
        return []

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
        blocks.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": data_url,
                },
            }
        )
    return blocks


def _sanitize_attachment_metadata(attachments):
    if not isinstance(attachments, list):
        return attachments
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


def run(input_data, context):
    store = ChatStore()
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")
    conv = store.get_conversation(conversation_id)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")
    message = input_data.get("message")
    if not message or not isinstance(message, dict):
        return error("message dict is required", "INVALID_INPUT")

    # --- 空メッセージ検証 ---
    raw_content = message.get("content")
    attachments = message.get("attachments")
    has_attachments = isinstance(attachments, list) and len(attachments) > 0
    if (raw_content is None or raw_content == "") and not has_attachments:
        return error("message content must not be empty", "INVALID_INPUT")
    if isinstance(raw_content, list) and len(raw_content) == 0 and not has_attachments:
        return error("message content must not be empty", "INVALID_INPUT")

    role = message.get("role", "user")
    content = message.get("content", [])
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
    user_msg_dict = {
        "role": role,
        "content": content,
        "metadata": metadata or None,
    }
    user_msg = store.add_message(conversation_id, user_msg_dict)
    if user_msg is None:
        return error("Failed to add user message", "INTERNAL_ERROR")
    chain = store.get_message_chain(conversation_id, user_msg["id"])
    standard_messages = convert_to_standard(chain)
    model = conv.get("model", "stub/default")

    # P1-4: Inspector 用のリクエストID を生成
    request_id = gen_id()
    manager = get_manager()
    system_prompt = _conversation_system_prompt(conv, manager)

    # --- 9b: ナレッジ / メモリ自動検索 & コンテキスト変数実動化 ---
    user_text = extract_user_text(content)
    input_data = _with_inferred_tools(input_data, _infer_requested_tools_from_message(user_text))
    try:
        enrich_info = enrich_messages(
            standard_messages, system_prompt, conversation_id, user_text, manager,
        )
    except Exception:
        # 補強処理全体が失敗してもフローを止めない
        enrich_info = {
            "knowledge_text": "",
            "memory_text": "",
            "knowledge_results": [],
            "memory_results": [],
            "enriched_prompt": system_prompt,
        }
        # fallback: system prompt を standard_messages に挿入
        if system_prompt:
            standard_messages.insert(0, {"role": "system", "content": system_prompt})

    # 防御ガード: enrich_messages が部分的に失敗し system メッセージ未挿入の場合を補完
    if system_prompt and (
        not standard_messages or standard_messages[0].get("role") != "system"
    ):
        standard_messages.insert(0, {"role": "system", "content": system_prompt})

    call_handler = context.get("call_handler") if context else None
    params = dict(input_data.get("params") or {})
    if "thinking_level" not in params:
        params["thinking_level"] = ModelRuntimeSettingsService().get_effective_thinking_level(
            profile_id=model,
            conversation_id=conversation_id,
        )["level"]
    request_context = dict(context or {})
    request_context["conversation_id"] = conversation_id
    request_context["conversation_workspace_dir"] = str(store.conversation_workspace_dir(conversation_id))
    request_context["model"] = model
    request_context["chat_params"] = params
    tool_policy = params.get("tool_policy")
    if isinstance(tool_policy, dict):
        request_context["profile_policy"] = {
            **(request_context.get("profile_policy") if isinstance(request_context.get("profile_policy"), dict) else {}),
            **tool_policy,
        }
    raw_tools, provider_tools, tool_context = _available_tools(request_context, input_data)
    tools_called = [tool_name_from_definition(tool) for tool in raw_tools if tool_name_from_definition(tool)]
    try:
        response = _complete_with_tools(
            model,
            standard_messages,
            provider_tools,
            tool_context,
            call_handler,
            params,
        )
    except RuntimeError as exc:
        return error(str(exc), "AI_ERROR")
    except Exception as exc:
        return error("AI request failed: " + str(exc), "AI_ERROR")

    # P1-4: Inspector にリクエストログを記録
    try:
        inspector = Inspector()
        inspector.log_request(
            request_id=request_id,
            conversation_id=conversation_id,
            model=model,
            prompt_used=enrich_info.get("enriched_prompt", system_prompt),
            tools_called=tools_called,
            context_info={
                "message_count": len(standard_messages),
                "messages": standard_messages,
                "source": "blocks.chat.send",
                "knowledge_results": enrich_info.get("knowledge_results", []),
                "memory_results": enrich_info.get("memory_results", []),
                "unknown_selected_tools": tool_context.get("unknown_selected_tools", []),
            },
        )
    except Exception:
        pass  # Inspector のエラーで本来の処理を止めない

    seq = user_msg.get("sequence_number", 1) + 1
    assistant_msg_dict = build_assistant_message(
        conversation_id=conversation_id,
        parent_id=user_msg["id"],
        sequence_number=seq,
        response=response,
        model=model,
    )
    assistant_msg = store.add_message(conversation_id, assistant_msg_dict)
    if assistant_msg is None:
        return error("Failed to add assistant message", "INTERNAL_ERROR")
    return ok(assistant_msg)
