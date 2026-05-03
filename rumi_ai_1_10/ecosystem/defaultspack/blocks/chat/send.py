import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.ai_client.client import AIClient
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


def _stub_response():
    return {
        "content": [{"type": "text", "text": "[stub] AI response placeholder"}],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


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
    payload.update(extra)
    return payload


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


def _append_tool_result_message(messages, tool_name, result, tool_call_id=""):
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
        if not tool_uses or step_index >= limit:
            break

        _append_assistant_tool_use_message(working_messages, tool_uses)
        for block in tool_uses:
            tool_name = str(block.get("name") or block.get("tool_name") or "")
            if not tool_name:
                continue
            arguments = _tool_arguments(block)
            events.append(
                _event(
                    "tool_call",
                    "{} を使用中".format(tool_name),
                    phase="tool_call",
                    tool_name=tool_name,
                    arguments=arguments,
                )
            )
            invoke_context = build_tool_execution_context(context or {}, tool_name, connected_names)
            if call_handler is not None:
                result = call_handler(
                    "defaults.tool.invoke",
                    {"tool_name": tool_name, "arguments": arguments},
                )
            else:
                from domain.tool.executor import ToolExecutor

                executed = ToolExecutor().execute(tool_name, arguments, invoke_context)
                result = {"status": "ok", "data": executed}
            log = {
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
                "timestamp": timestamp(),
            }
            tool_logs.append(log)
            events.append(
                _event(
                    "tool_result",
                    "{} の結果を受け取りました".format(tool_name),
                    phase="tool_result",
                    tool_name=tool_name,
                    is_error=isinstance(result, dict) and result.get("status") == "error",
                )
            )
            _append_tool_result_message(
                working_messages,
                tool_name,
                result,
                str(block.get("id") or block.get("tool_call_id") or ""),
            )

    response = response or _stub_response()
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
        metadata["attachments"] = attachments
        if isinstance(content, list):
            content.extend(_attachment_text_blocks(attachments))
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
    system_prompt = manager.get_system_prompt()

    # --- 9b: ナレッジ / メモリ自動検索 & コンテキスト変数実動化 ---
    user_text = extract_user_text(content)
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
    request_context = dict(context or {})
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
