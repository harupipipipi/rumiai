import sys
import os
import queue
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error
from domain.ai_client.client import AIClient
from domain.chat.store import ChatStore
from domain.chat.message_converter import convert_to_standard
from domain.chat.message_builder import build_assistant_message
from domain.prompt.manager import get_manager
from blocks.chat._context_helpers import extract_user_text, enrich_messages
from blocks.chat.send import (
    _attachment_image_blocks,
    _attachment_text_blocks,
    _conversation_system_prompt,
    _normalize_vision_detail,
    _sanitize_attachment_metadata,
)


class _InlineThoughtFilter:
    """Remove streamed <thought> blocks from visible text and keep them as metadata."""

    _open_tag = "<thought>"
    _close_tag = "</thought>"

    def __init__(self):
        self._buffer = ""
        self._in_thought = False
        self._thought_parts = []

    def push(self, text):
        self._buffer += str(text or "")
        visible = []
        while self._buffer:
            if self._in_thought:
                close_index = self._buffer.find(self._close_tag)
                if close_index == -1:
                    self._thought_parts.append(self._buffer)
                    self._buffer = ""
                    break
                self._thought_parts.append(self._buffer[:close_index])
                self._buffer = self._buffer[close_index + len(self._close_tag):]
                self._in_thought = False
                continue

            open_index = self._buffer.find(self._open_tag)
            if open_index != -1:
                visible.append(self._buffer[:open_index])
                self._buffer = self._buffer[open_index + len(self._open_tag):]
                self._in_thought = True
                continue

            keep = self._partial_open_tag_suffix_len(self._buffer)
            if keep:
                visible.append(self._buffer[:-keep])
                self._buffer = self._buffer[-keep:]
                break
            visible.append(self._buffer)
            self._buffer = ""
            break
        return "".join(visible)

    def finish(self):
        visible = ""
        if self._buffer:
            if self._in_thought:
                self._thought_parts.append(self._buffer)
            else:
                visible = self._buffer
        self._buffer = ""
        return visible

    def transcript(self):
        return "".join(self._thought_parts).strip()

    @classmethod
    def _partial_open_tag_suffix_len(cls, text):
        max_len = min(len(text), len(cls._open_tag) - 1)
        for size in range(max_len, 0, -1):
            if cls._open_tag.startswith(text[-size:]):
                return size
        return 0


def _fallback_send(input_data, context):
    from blocks.chat.send import run as send_run

    live_tool_events = bool((context or {}).get("stream_live_tool_events"))
    if live_tool_events:
        events_queue: queue.Queue = queue.Queue()
        sentinel = object()
        result_box = {}

        def event_callback(event):
            if isinstance(event, dict):
                events_queue.put(event)

        def worker():
            try:
                live_context = dict(context or {})
                live_context["event_callback"] = event_callback
                result_box["result"] = send_run(input_data, live_context)
            except Exception as exc:
                result_box["exception"] = exc
            finally:
                events_queue.put(sentinel)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            item = events_queue.get()
            if item is sentinel:
                break
            yield item
        if result_box.get("exception") is not None:
            yield {"type": "error", "error": "AI request failed: " + str(result_box["exception"])}
            return
        result = result_box.get("result")
    else:
        result = send_run(input_data, context)
    if isinstance(result, dict) and result.get("status") == "ok":
        message = result.get("data")
        if isinstance(message, dict):
            store = ChatStore()
            user_message = store.get_message(
                message.get("conversation_id"),
                message.get("parent_id"),
            )
            if user_message is not None and not live_tool_events:
                yield {"type": "user_message", "message": user_message}
            if not live_tool_events:
                for event in message.get("events") or []:
                    if isinstance(event, dict):
                        yield event
        yield {"type": "message", "message": message}
        yield {"type": "done", "message": message}
        return
    err = result.get("error", {}) if isinstance(result, dict) else {}
    yield {"type": "error", "error": err.get("message") or "AI request failed"}


def _stream_response(input_data, context):
    store = ChatStore()
    conversation_id = input_data.get("conversation_id")
    conv = store.get_conversation(conversation_id)
    message = input_data.get("message") if isinstance(input_data.get("message"), dict) else {}
    params = dict(input_data.get("params") or {})

    role = message.get("role", "user")
    raw_content = message.get("content", [])
    attachments = message.get("attachments")
    has_attachments = isinstance(attachments, list) and len(attachments) > 0
    content = raw_content
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
            content.extend(
                _attachment_image_blocks(
                    attachments,
                    _normalize_vision_detail(params.get("image_detail"), params.get("vision_detail")),
                )
            )

    user_msg = store.add_message(
        conversation_id,
        {
            "role": role,
            "content": content,
            "metadata": metadata or None,
        },
    )
    if user_msg is None:
        yield {"type": "error", "error": "Failed to add user message"}
        return
    yield {"type": "user_message", "message": user_msg}

    chain = store.get_message_chain(conversation_id, user_msg["id"])
    standard_messages = convert_to_standard(chain)
    model = conv.get("model", "stub/default")

    manager = get_manager()
    system_prompt = _conversation_system_prompt(conv, manager)
    user_text = extract_user_text(content)
    try:
        enrich_messages(standard_messages, system_prompt, conversation_id, user_text, manager)
    except Exception:
        if system_prompt:
            standard_messages.insert(0, {"role": "system", "content": system_prompt})
    if system_prompt and (
        not standard_messages or standard_messages[0].get("role") != "system"
    ):
        standard_messages.insert(0, {"role": "system", "content": system_prompt})

    client = AIClient()
    thought_filter = _InlineThoughtFilter()
    text_parts = []
    finish_reason = "stop"
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    try:
        chunks = client.stream(model, standard_messages, tools=[], params=params)
        for chunk in chunks:
            chunk_type = chunk.get("type", "") if isinstance(chunk, dict) else ""
            if chunk_type == "content_delta":
                delta = chunk.get("delta", {})
                text = delta.get("text", "")
                if text:
                    visible_text = thought_filter.push(text)
                    if visible_text:
                        text_parts.append(visible_text)
                        yield {"type": "delta", "delta": visible_text}
            elif chunk_type == "stream_end":
                finish_reason = chunk.get("finish_reason", "stop")
                usage = chunk.get("usage", usage)
    except Exception as exc:
        yield {"type": "error", "error": "AI request failed: " + str(exc)}
        return

    trailing_text = thought_filter.finish()
    if trailing_text:
        text_parts.append(trailing_text)
        yield {"type": "delta", "delta": trailing_text}

    response = {
        "content": [{"type": "text", "text": "".join(text_parts)}],
        "finish_reason": finish_reason,
        "usage": usage,
        "metadata": {
            "model": model,
            "attached_tool_count": 0,
            "attached_tools": [],
            "thinking": {"state": "completed"},
            "thinking_level": params.get("thinking_level"),
        },
    }
    transcript = thought_filter.transcript()
    if transcript:
        response["metadata"]["thinking"] = {
            "state": "completed",
            "transcript": transcript,
            "source": "inline_thought_stream",
        }

    seq = user_msg.get("sequence_number", 1) + 1
    assistant_msg = store.add_message(
        conversation_id,
        build_assistant_message(
            conversation_id=conversation_id,
            parent_id=user_msg["id"],
            sequence_number=seq,
            response=response,
            model=model,
        ),
    )
    if assistant_msg is None:
        yield {"type": "error", "error": "Failed to add assistant message"}
        return
    yield {"type": "message", "message": assistant_msg}
    yield {"type": "done", "message": assistant_msg}


def run(input_data, context):
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")
    store = ChatStore()
    conv = store.get_conversation(conversation_id)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")
    message = input_data.get("message")
    if not message or not isinstance(message, dict):
        return error("message dict is required", "INVALID_INPUT")

    raw_content = message.get("content")
    attachments = message.get("attachments")
    has_attachments = isinstance(attachments, list) and len(attachments) > 0
    if (raw_content is None or raw_content == "") and not has_attachments:
        return error("message content must not be empty", "INVALID_INPUT")
    if isinstance(raw_content, list) and len(raw_content) == 0 and not has_attachments:
        return error("message content must not be empty", "INVALID_INPUT")

    tools = input_data.get("tools")
    selected_tools = [item for item in tools if item] if isinstance(tools, list) else []
    client = AIClient()
    model = conv.get("model", "stub/default")
    if selected_tools or not client.supports_stream(model):
        live_context = dict(context or {})
        live_context["stream_live_tool_events"] = True
        return {"_sse": True, "events": _fallback_send(input_data, live_context)}
    return {"_sse": True, "events": _stream_response(input_data, context)}
