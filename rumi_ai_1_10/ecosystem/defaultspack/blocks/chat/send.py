import sys
import os
import base64
import json
import re
import time
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
_TRANSIENT_AI_ERROR_RE = re.compile(
    r"\b(429|500|502|503|504)\b|temporary|temporarily|timeout|timed out|try again|rate limit|internal error",
    re.IGNORECASE,
)
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


def _is_transient_ai_error(message):
    return bool(_TRANSIENT_AI_ERROR_RE.search(str(message or "")))


def _ai_direct_complete(model, messages, tools=None, params=None):
    """AIClient を直接呼び出して complete を実行する。
    APIキー未設定等で実プロバイダーがない場合は明示的エラーを返す。

    Returns:
        (response_dict, None) on success
        (None, error_message) on failure
    """
    client = AIClient()
    if not _has_real_provider(client, model):
        return None, "AI provider API key not configured"
    last_error = ""
    for attempt in range(3):
        try:
            response = client.complete(model, messages, tools or [], params or {})
            return response, None
        except RuntimeError as exc:
            last_error = str(exc)
            if attempt < 2 and _is_transient_ai_error(last_error):
                time.sleep(0.6 * (attempt + 1))
                continue
            return None, "AI request failed: " + last_error
    return None, "AI request failed: " + last_error


def _ai_error_after_tool_use_response(ai_error):
    message = str(ai_error or "AI request failed")
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    "tool 実行後に AI provider がエラーを返したため停止しました。"
                    "ここまでの tool ログとスクリーンショットは保存済みです。"
                    " reason: "
                    + message
                ),
            }
        ],
        "finish_reason": "ai_error_after_tool_use",
        "usage": {},
        "metadata": {
            "ai_error_after_tool_use": True,
            "ai_error": message,
            "transient_ai_error": _is_transient_ai_error(message),
        },
    }


def _stop_after_tool_ai_error(events, context, ai_error):
    _append_event(
        events,
        context,
        _event(
            "status",
            "tool 実行後の AI provider エラーで停止しました",
            phase="ai_error_after_tool_use",
            ai_error=str(ai_error or "AI request failed"),
            transient_ai_error=_is_transient_ai_error(ai_error),
        ),
    )
    return _ai_error_after_tool_use_response(ai_error)


def _event(event_type, message, **extra):
    payload = {
        "type": event_type,
        "message": message,
        "timestamp": timestamp(),
    }
    payload.update(_redact_sensitive_value(extra))
    return payload


class _ChatCancelled(Exception):
    pass


def _is_cancelled(context):
    checker = (context or {}).get("is_cancelled") if isinstance(context, dict) else None
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return False


def _raise_if_cancelled(context):
    if _is_cancelled(context):
        raise _ChatCancelled()


def _append_event(events, context, event):
    events.append(event)
    persist_callback = (context or {}).get("stream_event_persist_callback") if isinstance(context, dict) else None
    if callable(persist_callback):
        try:
            persist_callback(list(events), event)
        except Exception:
            pass
    callback = (context or {}).get("stream_event_callback") if isinstance(context, dict) else None
    if callable(callback):
        try:
            callback(event)
        except Exception:
            pass


def _is_stream_fallback_context(context):
    if not isinstance(context, dict):
        return False
    return callable(context.get("stream_event_callback")) and callable(context.get("is_cancelled"))


def _assistant_raw_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return " ".join(parts)


def _create_stream_assistant_draft(store, conversation_id, user_msg, model, params):
    seq = user_msg.get("sequence_number", 1) + 1
    return store.add_message(
        conversation_id,
        {
            "role": "assistant",
            "parent_id": user_msg["id"],
            "sequence_number": seq,
            "content": [],
            "raw_text": "",
            "finish_reason": "streaming",
            "usage": {},
            "widget": None,
            "metadata": {
                "model": model,
                "streaming": True,
                "draft": True,
                "thinking": {"state": "running"},
                "thinking_level": (params or {}).get("thinking_level"),
            },
            "events": [],
            "tool_logs": [],
            "model": model,
        },
    )


def _stream_draft_event_persister(store, conversation_id, draft_id, model, params):
    def persist(events, _event):
        draft = store.get_message(conversation_id, draft_id)
        metadata = dict((draft or {}).get("metadata") or {})
        metadata.update(
            {
                "model": model,
                "streaming": True,
                "draft": True,
                "thinking": {"state": "running"},
                "thinking_level": (params or {}).get("thinking_level"),
            }
        )
        store.update_message(
            conversation_id,
            draft_id,
            {
                "events": events,
                "metadata": metadata,
                "finish_reason": "streaming",
            },
        )

    return persist


def _final_assistant_updates(assistant_msg_dict):
    updates = dict(assistant_msg_dict)
    content = updates.get("content", [])
    updates["raw_text"] = _assistant_raw_text(content)
    metadata = dict(updates.get("metadata") or {})
    metadata.pop("streaming", None)
    metadata.pop("draft", None)
    updates["metadata"] = metadata
    return updates


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


def _computer_use_preferences_from_text(user_text):
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


def _apply_computer_use_context_preferences(context, user_text):
    updated = dict(context or {})
    preferences = _computer_use_preferences_from_text(user_text)
    for key, value in preferences.items():
        if value not in (None, "", False):
            updated[key] = value
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


def _prefocus_computer_use_target_window(available_tools, base_context, *, call_handler=None):
    if not isinstance(base_context, dict) or not base_context.get("user_requested_computer_use"):
        return None
    target_app = str(base_context.get("computer_use_target_app") or "").strip()
    target_title = str(base_context.get("computer_use_target_title") or "").strip()
    if not (target_app or target_title):
        return None
    connected_names = connected_tool_names(
        available_tools,
        base_context.get("runtime_profile") if isinstance(base_context.get("runtime_profile"), dict) else None,
        agent_id=base_context.get("agent_id"),
    )
    tool_name = next(
        (candidate for candidate in ("browser_computer", "computer_use", "browser_use") if candidate in connected_names),
        "",
    )
    if not tool_name:
        return None

    payload = {}
    if target_app:
        payload["app"] = target_app
    if target_title:
        payload["title"] = target_title
    arguments = {"action": "computer.select_window", "payload": payload}
    invoke_context = build_tool_execution_context(base_context, tool_name, connected_names)
    if call_handler is not None:
        result = call_handler(
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


def _tool_limit_message(limit, tool_uses):
    names = []
    for block in tool_uses:
        name = str(block.get("name") or block.get("tool_name") or "").strip()
        if name:
            names.append(name)
    suffix = " pending_tools=" + ", ".join(names) if names else ""
    return (
        "tool call の上限に達したため停止しました。"
        "同じ依頼を続ける場合は、もう一度送信してください。"
        f" (max_tool_calls: {limit}{suffix})"
    )


def _tool_result_data(result):
    if not isinstance(result, dict):
        return {}
    data = result.get("data", result)
    return data if isinstance(data, dict) else {}


def _tool_result_reason(result):
    if not isinstance(result, dict):
        return ""
    data = _tool_result_data(result)
    for source in (data, result):
        if not isinstance(source, dict):
            continue
        for key in ("reason", "message", "result", "summary"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        error_value = source.get("error")
        if isinstance(error_value, dict):
            message = error_value.get("message") or error_value.get("reason")
            if isinstance(message, str) and message.strip():
                return message.strip()
        elif isinstance(error_value, str) and error_value.strip():
            return error_value.strip()
    return ""


def _tool_result_is_error(result):
    if not isinstance(result, dict):
        return False
    if result.get("status") == "error":
        return True
    data = _tool_result_data(result)
    if data.get("status") == "error" or data.get("is_error") is True:
        return True
    widget = data.get("widget") if isinstance(data.get("widget"), dict) else {}
    return widget.get("is_error") is True


def _find_tool_recovery(value):
    if isinstance(value, dict):
        recovery = value.get("recovery")
        if isinstance(recovery, dict):
            return recovery
        widget = value.get("widget")
        if isinstance(widget, dict):
            recovery = widget.get("recovery")
            if isinstance(recovery, dict):
                return recovery
        data = value.get("data")
        if isinstance(data, dict):
            recovery = _find_tool_recovery(data)
            if recovery:
                return recovery
        error_value = value.get("error")
        if isinstance(error_value, dict):
            recovery = _find_tool_recovery(error_value)
            if recovery:
                return recovery
    return {}


def _tool_result_recovery_kind(result):
    recovery = _find_tool_recovery(result)
    kind = str(recovery.get("kind") or "").strip()
    if kind:
        return kind
    reason = _tool_result_reason(result).lower()
    if "visible window" in reason or "background computer-use is disabled" in reason:
        return "visible_window_required"
    return ""


def _message_content_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _tool_blocked_response(tool_name, result):
    recovery = _find_tool_recovery(result)
    kind = str(recovery.get("kind") or "").strip()
    if not kind:
        kind = _tool_result_recovery_kind(result)
    reason = _tool_result_reason(result)
    if kind in {"visible_window_required", "focus_required"}:
        message = (
            f"{tool_name} は現在表示されている画面だけを操作する設定のため停止しました。"
            + (f" reason: {reason}" if reason else "")
        )
    else:
        message = (
            f"{tool_name} が回復不能な tool ブロックを返したため停止しました。"
            + (f" reason: {reason}" if reason else "")
        )
    return {
        "content": [{"type": "text", "text": message}],
        "finish_reason": "tool_blocked",
        "usage": {},
        "metadata": {
            "tool_blocked": True,
            "tool_blocked_tool": tool_name,
            "tool_blocked_kind": kind,
            "tool_blocked_recovery": recovery,
        },
    }


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
        return (
            "Browser/computer screenshot attached for the vision model. "
            "For point actions, pass only normalized_x and normalized_y values from 0 to 1000 relative to the attached image. "
            "Do not return screen pixels or action coordinates, and do not do scale conversion. "
            "The harness converts normalized attached-image coordinates to action/screen coordinates."
        )
    data = result.get("data", result)
    if not isinstance(data, dict):
        return (
            "Browser/computer screenshot attached for the vision model. "
            "For point actions, pass only normalized_x and normalized_y values from 0 to 1000 relative to the attached image. "
            "Do not return screen pixels or action coordinates, and do not do scale conversion. "
            "The harness converts normalized attached-image coordinates to action/screen coordinates."
        )
    widget = data.get("widget") if isinstance(data.get("widget"), dict) else {}
    source = widget if (widget.get("coordinate_system") or widget.get("model_image_size")) else data
    model_image_size = source.get("model_image_size") if isinstance(source.get("model_image_size"), dict) else {}
    parts = ["Browser/computer screenshot attached for the vision model."]
    active_window = _tool_window_details(result, "active_window")
    selected_window = (
        _tool_window_details(result, "selected_window")
        or _tool_window_details(result, "target_window")
    )
    if active_window:
        parts.append("Foreground window: {}.".format(active_window))
    if selected_window:
        parts.append("Selected target window: {}.".format(selected_window))
        if active_window and selected_window != active_window:
            parts.append(
                "Foreground and selected target differ, so refocus the target window before typing, key presses, scrolling, or send actions."
            )
    if model_image_size.get("width") and model_image_size.get("height"):
        parts.append(
            "The attached model image size (model_image_size) is width={} height={}.".format(
                model_image_size.get("width"),
                model_image_size.get("height"),
            )
        )
    else:
        parts.append("Use the attached image itself as the coordinate reference.")
    if isinstance(source.get("crop_reference"), dict) or isinstance(data.get("crop_reference"), dict):
        parts.append(
            "This is a cropped or zoomed screenshot; normalized coordinates are relative only to this attached crop, not the previous full screenshot."
        )
    parts.append(
        "For point actions, pass only normalized_x and normalized_y values from 0 to 1000 relative to the attached image."
    )
    parts.append(
        "Do not return screen pixels, image_size pixels, or action coordinates; do not use image_size, "
        "action_coordinate_system, or model_to_action_scale; and do not do scale conversion."
    )
    parts.append("The harness converts normalized attached-image coordinates to action/screen coordinates.")
    parts.append(
        "If the target is small or ambiguous, call screenshot with crop/zoom first. "
        "source=latest crops from the last full or selected-window screenshot so you do not get trapped inside a previous crop; "
        "use source=current_crop only when you intentionally want to crop the current attached crop again. "
        "After a zoomed/cropped view, request a fresh screenshot before unrelated actions."
    )
    return " ".join(parts)


def _tool_result_message_text(tool_name, result):
    if isinstance(result, dict):
        data = result.get("data", result)
        if isinstance(data, dict):
            if tool_name in {"browser_companion", "browser_computer", "browser_use", "computer_use"}:
                result_text = json.dumps(_compact_tool_log_value(data), ensure_ascii=False)
            else:
                result_text = str(data.get("result", data.get("summary", json.dumps(data, ensure_ascii=False))))
        else:
            result_text = str(data)
    else:
        result_text = str(result)
    max_chars = 12000
    if len(result_text) > max_chars:
        return result_text[:max_chars] + "\n[tool result truncated]"
    return result_text


def _append_tool_result_message(messages, tool_name, result, tool_call_id="", *, model=""):
    result_text = _tool_result_message_text(tool_name, result)
    messages.append(
        {
            "role": "tool",
            "name": tool_name,
            "tool_call_id": tool_call_id,
            "content": result_text,
        }
    )
    if (
        tool_name in {"browser_companion", "browser_computer", "browser_use", "computer_use"}
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


def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "debug", "enabled"}
    return False


def _frontend_debug_settings_enabled():
    try:
        settings_path = Path(__file__).resolve().parents[2] / "user_data" / "shared" / "frontend_settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    debug = settings.get("debug") if isinstance(settings, dict) else {}
    if not isinstance(debug, dict):
        return False
    return _truthy(debug.get("ai_request_logging") or debug.get("enabled"))


def _ai_debug_enabled(input_data=None, params=None, context=None):
    if _truthy(os.environ.get("RUMI_DEFAULTSPACK_AI_DEBUG")):
        return True
    for source in (context, params, input_data):
        if not isinstance(source, dict):
            continue
        for key in ("ai_debug_enabled", "ai_debug", "debug_mode", "debug", "log_ai_requests"):
            if key in source and _truthy(source.get(key)):
                return True
    return _frontend_debug_settings_enabled()


def _ai_debug_log_dir(context):
    workspace = (context or {}).get("conversation_workspace_dir") if isinstance(context, dict) else None
    if isinstance(workspace, str) and workspace.strip():
        return Path(workspace) / "debug" / "ai_requests"
    return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "chat" / "debug" / "ai_requests"


def _debug_image_suffix(mime_type):
    subtype = str(mime_type or "").split("/", 1)[-1].split(";", 1)[0].lower()
    if subtype in {"jpeg", "jpg"}:
        return ".jpg"
    if subtype in {"png", "gif", "webp"}:
        return "." + subtype
    return ".img"


def _save_debug_data_image(data_url, debug_dir, request_key, images):
    header, separator, encoded = str(data_url or "").partition(",")
    if not separator:
        return "[invalid image data_url]"
    mime_type = header[5:].split(";", 1)[0] if header.startswith("data:") else "image/png"
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        return "[invalid image data_url]"
    index = len(images) + 1
    path = debug_dir / "{}-image-{}{}".format(request_key, index, _debug_image_suffix(mime_type))
    try:
        path.write_bytes(raw)
    except OSError:
        return "[failed to save image data_url]"
    record = {
        "path": str(path),
        "mime_type": mime_type,
        "bytes": len(raw),
    }
    images.append(record)
    return {
        "url": "[image data saved as artifact]",
        "debug_image_path": str(path),
        "mime_type": mime_type,
        "bytes": len(raw),
    }


def _debug_sanitize_ai_payload(value, debug_dir, request_key, images, *, parent_key=""):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = _debug_sanitize_ai_payload(
                    item,
                    debug_dir,
                    request_key,
                    images,
                    parent_key=key_text,
                )
        return sanitized
    if isinstance(value, list):
        return [
            _debug_sanitize_ai_payload(item, debug_dir, request_key, images, parent_key=parent_key)
            for item in value
        ]
    if isinstance(value, str):
        if parent_key and _SECRET_KEY_RE.search(parent_key):
            return "[redacted]"
        if value.startswith(_DATA_IMAGE_PREFIX):
            return _save_debug_data_image(value, debug_dir, request_key, images)
    return value


def _write_debug_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _log_ai_debug_request(context, *, model, messages, tools, params, step_index, reason=""):
    if not _ai_debug_enabled(params=params, context=context):
        return None
    debug_dir = _ai_debug_log_dir(context)
    debug_dir.mkdir(parents=True, exist_ok=True)
    step_label = str(step_index)
    request_key = "ai-{}-step-{}".format(int(time.time() * 1000), re.sub(r"[^A-Za-z0-9_.-]+", "_", step_label))
    images = []
    payload = {
        "schema_version": 1,
        "kind": "ai_request_debug_log",
        "created_at": timestamp(),
        "model": model,
        "step_index": step_index,
        "reason": reason,
        "messages": _debug_sanitize_ai_payload(messages, debug_dir, request_key, images),
        "tools": _debug_sanitize_ai_payload(tools, debug_dir, request_key, images),
        "params": _debug_sanitize_ai_payload(params, debug_dir, request_key, images),
        "images": images,
    }
    path = debug_dir / "{}.json".format(request_key)
    try:
        _write_debug_json(path, payload)
    except OSError:
        return None
    return str(path)


def _append_ai_debug_response(path, response):
    if not path:
        return
    try:
        debug_path = Path(path)
        payload = json.loads(debug_path.read_text(encoding="utf-8"))
        images = payload.get("response_images")
        if not isinstance(images, list):
            images = []
        payload["response_logged_at"] = timestamp()
        payload["response"] = _debug_sanitize_ai_payload(
            response,
            debug_path.parent,
            debug_path.stem + "-response",
            images,
        )
        if images:
            payload["response_images"] = images
        _write_debug_json(debug_path, payload)
    except Exception:
        pass


def _truncate_text(value, limit=480):
    text = str(value or "").strip()
    if len(text) > limit:
        return text[: max(0, limit - 3)] + "..."
    return text


def _tool_window_details(result, key):
    if not isinstance(result, dict):
        return ""
    data = _tool_result_data(result)
    widget = data.get("widget") if isinstance(data.get("widget"), dict) else {}
    candidates = []
    for container in (data, widget):
        if not isinstance(container, dict):
            continue
        window = container.get(key)
        if isinstance(window, dict):
            candidates.append(window)
    for window in candidates:
        app = _truncate_text(window.get("app"), limit=80)
        title = _truncate_text(window.get("title"), limit=140)
        if app and title:
            return "{} | {}".format(app, title)
        if title:
            return title
        if app:
            return app
    return ""


def _tool_result_summary(tool_name, result):
    reason = _tool_result_reason(result)
    if reason:
        return _truncate_text(reason)
    data = _tool_result_data(result)
    if tool_name in {"browser_computer", "browser_use", "computer_use"}:
        active_window = _tool_window_details(result, "active_window")
        selected_window = (
            _tool_window_details(result, "selected_window")
            or _tool_window_details(result, "target_window")
        )
        if active_window and selected_window and active_window != selected_window:
            return _truncate_text(
                "{} completed. Foreground: {}. Selected target: {}.".format(
                    tool_name,
                    active_window,
                    selected_window,
                )
            )
        if active_window:
            return _truncate_text("{} completed on {}.".format(tool_name, active_window))
        if selected_window:
            return _truncate_text("{} completed with target {}.".format(tool_name, selected_window))
    for key in ("results", "items", "files", "screenshots"):
        value = data.get(key)
        if isinstance(value, list):
            return "{} returned {} {}".format(tool_name, len(value), key)
    if _tool_result_is_error(result):
        return "{} failed".format(tool_name)
    return "{} completed".format(tool_name)


def _artifact_kind_for_path(path):
    suffix = Path(str(path or "")).suffix.lower()
    return "image" if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"} else "file"


def _tool_result_artifacts(value, artifacts=None, seen=None):
    artifacts = artifacts if isinstance(artifacts, list) else []
    seen = seen if isinstance(seen, set) else set()
    if isinstance(value, dict):
        preferred_path = ""
        for key in ("model_image_path", "screenshot_path", "path"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                preferred_path = item.strip()
                break
        if preferred_path and preferred_path not in seen:
            seen.add(preferred_path)
            artifacts.append(
                {
                    "name": Path(preferred_path).name or "artifact",
                    "path": preferred_path,
                    "kind": _artifact_kind_for_path(preferred_path),
                }
            )
        for key, item in value.items():
            if key in {"path", "screenshot_path", "model_image_path", "data_url", "dataUrl"}:
                continue
            _tool_result_artifacts(item, artifacts, seen)
    elif isinstance(value, list):
        for item in value:
            _tool_result_artifacts(item, artifacts, seen)
    return artifacts


def _bounded_compact_tool_result(result, summary, artifacts, limit=6000):
    compact = _compact_tool_log_value(result)
    try:
        encoded = json.dumps(compact, ensure_ascii=False)
    except Exception:
        encoded = str(compact)
    if len(encoded) <= limit:
        return compact
    return {
        "summary": summary,
        "artifacts": artifacts,
        "truncated": True,
    }


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
    guidance = ""
    tool_names = {tool_name_from_definition(tool) for tool in tools or []}
    if tool_names.intersection({"browser_companion", "browser_computer", "browser_use", "computer_use"}):
        guidance = (
            " Browser tool rules: browser_companion is the DOM-aware extension path and can inspect paired browser tabs with the user's live session; "
            "browser_computer/computer_use are visible-window computer-use paths, so use apps/windows plus select_app/select_window to target Vivaldi, VS Code, Finder, LINE, Chrome, or any other visible app/window; "
            "when you need background-tab DOM access, element ids, or the user's signed-in browser session, prefer browser_companion; "
            "for visible-window actions, inspect app state with context before screenshots; "
            "for visual clicks, use a zoom ladder: first take a full or selected-window screenshot, then when the target is small or ambiguous call screenshot again with crop/zoom around the likely region; source=latest crops from that last full/selected-window screenshot, while source=current_crop is only for intentionally cropping the current crop again; click only using normalized_x/normalized_y relative to the attached image; "
            "after a zoomed/cropped inspection, take a fresh full or selected-window screenshot before unrelated actions so stale crop coordinates are not reused; "
            "prefer one type call for words like hello and key only for shortcuts/return; "
            "click/move without physical=true only moves the virtual AI cursor and does not move the user's mouse."
        )
    return {
        "role": "system",
        "content": (
            "Available tools are connected for this turn. "
            "Use them when they are relevant, and do not claim that no tools are available. "
            "Connected tools: " + "; ".join(names) + guidance
        ),
    }


def _complete_with_tools(model, messages, tools, context, call_handler, params):
    events = []
    _append_event(events, context, _event("status", "{} が考えています".format(model), phase="thinking", model=model))
    tool_logs = []
    debug_logs = []
    if tools:
        _append_event(
            events,
            context,
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
    if limit == 4 and connected_names.intersection({"browser_companion", "browser_computer", "browser_use", "computer_use"}):
        limit = 12

    blocked_response = None
    for step_index in range(max(1, limit + 1)):
        _raise_if_cancelled(context)
        ai_params = {
            "model": model,
            "messages": working_messages,
            "tools": tools,
            "params": params,
        }
        debug_request_path = _log_ai_debug_request(
            context,
            model=model,
            messages=working_messages,
            tools=tools,
            params=params,
            step_index=step_index + 1,
        )
        if debug_request_path:
            debug_logs.append(debug_request_path)
            _append_event(
                events,
                context,
                _event(
                    "status",
                    "AI debug log を保存しました",
                    phase="ai_debug",
                    debug_log_path=debug_request_path,
                    step_index=step_index + 1,
                ),
            )
        if call_handler is not None:
            response = call_handler("defaults.ai.complete", ai_params)
            if isinstance(response, dict) and response.get("status") == "error":
                err = response.get("error", {})
                ai_error = str(err.get("message") or "AI request failed")
                _append_ai_debug_response(debug_request_path, {"status": "error", "error": err})
                if tool_logs:
                    response = _stop_after_tool_ai_error(events, context, ai_error)
                    break
                raise RuntimeError(ai_error)
            if isinstance(response, dict) and response.get("status") == "ok":
                response = response.get("data", {})
        else:
            response, ai_error = _ai_direct_complete(model, working_messages, tools, params)
            if ai_error is not None:
                _append_ai_debug_response(debug_request_path, {"status": "error", "error": ai_error})
                if tool_logs:
                    response = _stop_after_tool_ai_error(events, context, ai_error)
                    break
                raise RuntimeError(ai_error)
        _append_ai_debug_response(debug_request_path, response)
        _raise_if_cancelled(context)

        if not isinstance(response, dict):
            response = _stub_response()
        tool_uses = _tool_use_blocks(response)
        if not tool_uses and not _response_text(response).strip():
            retry_params = _params_without_thinking(params)
            if retry_params != params:
                retry_response = None
                retry_debug_path = _log_ai_debug_request(
                    context,
                    model=model,
                    messages=working_messages,
                    tools=tools,
                    params=retry_params,
                    step_index="{}-retry-no-thinking".format(step_index + 1),
                    reason="empty_response_retry_without_thinking",
                )
                if retry_debug_path:
                    debug_logs.append(retry_debug_path)
                    _append_event(
                        events,
                        context,
                        _event(
                            "status",
                            "AI debug log を保存しました",
                            phase="ai_debug",
                            debug_log_path=retry_debug_path,
                            step_index="{}-retry-no-thinking".format(step_index + 1),
                        ),
                    )
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
                        _append_ai_debug_response(retry_debug_path, {"status": "error", "error": ai_error})
                        retry_response = None
                _append_ai_debug_response(retry_debug_path, retry_response)
                if isinstance(retry_response, dict) and (
                    _response_text(retry_response).strip() or _tool_use_blocks(retry_response)
                ):
                    retry_metadata = dict(retry_response.get("metadata") or {})
                    retry_metadata["recovered_from_empty_response"] = True
                    retry_response["metadata"] = retry_metadata
                    response = retry_response
                    tool_uses = _tool_use_blocks(response)
        if tool_uses and step_index >= limit:
            response = {
                "content": [{"type": "text", "text": _tool_limit_message(limit, tool_uses)}],
                "finish_reason": "tool_call_limit",
                "usage": response.get("usage", {}) if isinstance(response, dict) else {},
                "metadata": {
                    "max_tool_calls_reached": True,
                    "pending_tool_uses": [
                        {
                            "name": str(block.get("name") or block.get("tool_name") or ""),
                            "id": str(block.get("id") or block.get("tool_call_id") or ""),
                        }
                        for block in tool_uses
                    ],
                },
            }
            _append_event(
                events,
                context,
                _event(
                    "status",
                    "tool call の上限に達したため停止しました",
                    phase="tool_call_limit",
                    tool_count=len(tool_logs),
                    max_tool_calls=limit,
                )
            )
            break
        if not tool_uses:
            break

        _append_assistant_tool_use_message(working_messages, tool_uses)
        for block in tool_uses:
            _raise_if_cancelled(context)
            tool_name = str(block.get("name") or block.get("tool_name") or "")
            if not tool_name:
                continue
            tool_call_id = str(block.get("id") or block.get("tool_call_id") or gen_id())
            arguments = _tool_arguments(block)
            _append_event(
                events,
                context,
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
            _raise_if_cancelled(context)
            log = {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": _redact_sensitive_value(arguments),
                "result": _compact_tool_log_value(result),
                "timestamp": timestamp(),
            }
            tool_logs.append(log)
            result_summary = _tool_result_summary(tool_name, result)
            artifacts = _tool_result_artifacts(result)
            _append_event(
                events,
                context,
                _event(
                    "tool_call_completed",
                    result_summary or "{} の結果を受け取りました".format(tool_name),
                    phase="tool_call_completed",
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    is_error=_tool_result_is_error(result),
                    recovery_kind=_tool_result_recovery_kind(result),
                    result_summary=result_summary,
                    summary=result_summary,
                    result=_bounded_compact_tool_result(result, result_summary, artifacts),
                    artifacts=artifacts,
                    artifact_paths=[artifact.get("path") for artifact in artifacts if artifact.get("path")],
                )
            )
            _append_tool_result_message(
                working_messages,
                tool_name,
                result,
                tool_call_id,
                model=model,
            )
            recovery_kind = _tool_result_recovery_kind(result)
            if recovery_kind in {"visible_window_required", "focus_required"}:
                blocked_response = _tool_blocked_response(tool_name, result)
                _append_event(
                    events,
                    context,
                    _event(
                        "status",
                        "可視画面外の tool 実行要求のため停止しました",
                        phase="tool_blocked",
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        recovery_kind=recovery_kind,
                    )
                )
                break
        if blocked_response is not None:
            response = blocked_response
            break

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
    if debug_logs:
        metadata["ai_debug"] = {
            "enabled": True,
            "request_logs": debug_logs,
        }
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
    inferred_tool_ids = _infer_requested_tools_from_message(user_text)
    input_data = _with_inferred_tools(input_data, inferred_tool_ids)
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
    if _ai_debug_enabled(input_data=input_data, params=params, context=request_context):
        request_context["ai_debug_enabled"] = True
    if inferred_tool_ids:
        request_context["user_requested_computer_use"] = True
        request_context = _apply_computer_use_context_preferences(request_context, user_text)
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
    stream_assistant_draft = None
    if _is_stream_fallback_context(request_context):
        stream_assistant_draft = _create_stream_assistant_draft(
            store,
            conversation_id,
            user_msg,
            model,
            params,
        )
        if stream_assistant_draft is None:
            return error("Failed to add assistant draft", "INTERNAL_ERROR")
        request_context["stream_event_persist_callback"] = _stream_draft_event_persister(
            store,
            conversation_id,
            stream_assistant_draft["id"],
            model,
            params,
        )
    raw_tools, provider_tools, tool_context = _available_tools(request_context, input_data)
    tools_called = [tool_name_from_definition(tool) for tool in raw_tools if tool_name_from_definition(tool)]
    try:
        _prefocus_computer_use_target_window(raw_tools, tool_context, call_handler=call_handler)
    except Exception:
        pass
    try:
        response = _complete_with_tools(
            model,
            standard_messages,
            provider_tools,
            tool_context,
            call_handler,
            params,
        )
    except _ChatCancelled:
        return error("Chat request cancelled", "CANCELLED")
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
    if stream_assistant_draft is not None:
        assistant_msg = store.update_message(
            conversation_id,
            stream_assistant_draft["id"],
            _final_assistant_updates(assistant_msg_dict),
        )
    else:
        assistant_msg = store.add_message(conversation_id, assistant_msg_dict)
    if assistant_msg is None:
        return error("Failed to add assistant message", "INTERNAL_ERROR")
    return ok(assistant_msg)
