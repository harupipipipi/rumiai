import sys
import os
import queue
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error
from domain.ai_client.client import AIClient
from domain.chat.store import ChatStore
from domain.chat.cancellation import get_chat_cancellation_registry
from domain.chat.message_converter import convert_to_standard
from domain.chat.message_builder import build_assistant_message
from domain.prompt.manager import get_manager
from blocks.chat._context_helpers import extract_user_text, enrich_messages
from blocks.chat.send import (
    _ai_error_response,
    _ai_retry_attempts,
    _ai_retry_delay,
    _attachment_image_blocks,
    _attachment_text_blocks,
    _apply_computer_use_context_preferences,
    _conversation_system_prompt,
    _event,
    _infer_requested_tools_from_message,
    _is_retryable_ai_error,
    _sanitize_attachment_metadata,
    _with_inferred_tools,
)


class _InlineThoughtFilter:
    """Remove streamed <thought> blocks from visible text and keep them as metadata."""

    _open_tag = "<thought>"
    _close_tag = "</thought>"

    def __init__(self):
        self._buffer = ""
        self._in_thought = False
        self._thought_parts = []
        self._streamed_thought_len = 0

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

    def pending_thinking_delta(self):
        thought_text = "".join(self._thought_parts)
        delta = thought_text[self._streamed_thought_len:]
        self._streamed_thought_len = len(thought_text)
        return delta

    @classmethod
    def _partial_open_tag_suffix_len(cls, text):
        max_len = min(len(text), len(cls._open_tag) - 1)
        for size in range(max_len, 0, -1):
            if cls._open_tag.startswith(text[-size:]):
                return size
        return 0


def _text_from_content_blocks(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts).strip()


def _params_without_thinking(params):
    retry_params = dict(params or {})
    for key in ("thinking", "thinking_level", "reasoning_effort"):
        retry_params.pop(key, None)
    return retry_params


def _empty_stream_message(finish_reason):
    reason = str(finish_reason or "unknown").strip() or "unknown"
    return (
        "モデルから本文のない応答が返りました。"
        "もう一度送信するか、thinkingを「なし」にして試してください。"
        f" (finish_reason: {reason})"
    )


def _fallback_complete_without_thinking(client, model, messages, params, transcript=""):
    try:
        response = client.complete(model, messages, tools=[], params=_params_without_thinking(params))
    except Exception:
        return None
    if not isinstance(response, dict) or not _text_from_content_blocks(response.get("content")):
        return None
    metadata = dict(response.get("metadata") or {})
    if transcript:
        metadata["thinking"] = {
            "state": "completed",
            "transcript": transcript,
            "source": "inline_thought_stream",
        }
    else:
        metadata.setdefault("thinking", {"state": "completed"})
    metadata["recovered_from_empty_stream"] = True
    metadata.setdefault("model", model)
    metadata.setdefault("attached_tool_count", 0)
    metadata.setdefault("attached_tools", [])
    metadata["thinking_level"] = params.get("thinking_level")
    response["metadata"] = metadata
    return response


def _fallback_send(input_data, context):
    event_queue = queue.Queue()
    done = object()
    cancel_event = threading.Event()
    result_box = {}
    conversation_id = str(input_data.get("conversation_id") or "")
    cancellation_registry = get_chat_cancellation_registry()

    def emit_event(event):
        event_queue.put(event)

    def is_cancelled():
        return cancel_event.is_set() or cancellation_registry.is_cancelled(conversation_id)

    def request_cancel():
        cancel_event.set()

    def worker():
        from blocks.chat.send import run as send_run

        try:
            stream_context = dict(context or {})
            stream_context["stream_event_callback"] = emit_event
            stream_context["is_cancelled"] = is_cancelled
            result_box["result"] = send_run(input_data, stream_context)
        except BaseException as exc:
            result_box["exception"] = exc
        finally:
            event_queue.put(done)

    thread = threading.Thread(target=worker, daemon=True)
    cancellation_registry.register(conversation_id, request_cancel)
    thread.start()
    try:
        while True:
            event = event_queue.get()
            if event is done:
                break
            yield event
    finally:
        cancel_event.set()
        cancellation_registry.unregister(conversation_id, request_cancel)

    if "exception" in result_box:
        yield {"type": "error", "error": "AI request failed: " + str(result_box["exception"])}
        return

    result = result_box.get("result")
    if isinstance(result, dict) and result.get("status") == "ok":
        message = result.get("data")
        yield {"type": "message", "message": message}
        yield {"type": "done", "message": message}
        return
    err = result.get("error", {}) if isinstance(result, dict) else {}
    yield {"type": "error", "error": err.get("message") or "AI request failed"}


def _stream_response(input_data, context):
    store = ChatStore()
    conversation_id = str(input_data.get("conversation_id") or "")
    conv = store.get_conversation(conversation_id)
    message = input_data.get("message") if isinstance(input_data.get("message"), dict) else {}
    cancellation_registry = get_chat_cancellation_registry()
    cancel_event = threading.Event()
    chunks = None

    def is_cancelled():
        return cancel_event.is_set() or cancellation_registry.is_cancelled(conversation_id)

    def request_cancel():
        cancel_event.set()
        close = getattr(chunks, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    def emit_cancelled():
        yield {"type": "error", "error": "cancelled"}

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
            content.extend(_attachment_image_blocks(attachments))

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
    cancellation_registry.register(conversation_id, request_cancel)

    params = dict(input_data.get("params") or {})
    model = (conv or {}).get("model", "stub/default")
    seq = user_msg.get("sequence_number", 1) + 1
    assistant_msg = store.add_message(
        conversation_id,
        build_assistant_message(
            conversation_id=conversation_id,
            parent_id=user_msg["id"],
            sequence_number=seq,
            response={
                "content": [{"type": "text", "text": ""}],
                "finish_reason": "streaming",
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "metadata": {
                    "model": model,
                    "attached_tool_count": 0,
                    "attached_tools": [],
                    "thinking": {"state": "running"},
                    "thinking_level": params.get("thinking_level"),
                },
                "events": [],
                "tool_logs": [],
            },
            model=model,
        ),
    )
    if assistant_msg is None:
        cancellation_registry.unregister(conversation_id, request_cancel)
        yield {"type": "error", "error": "Failed to create assistant message"}
        return

    assistant_events = []

    def current_transcript():
        return "\n".join(
            part
            for part in ["".join(provider_thinking_parts).strip(), thought_filter.transcript()]
            if part
        ).strip()

    def update_assistant_draft(*, finish="streaming", thinking_state="running", usage_data=None, extra_metadata=None):
        current_text = "".join(text_parts)
        thinking = {"state": thinking_state}
        transcript = current_transcript()
        if transcript:
            thinking["transcript"] = transcript
        metadata = {
            "model": model,
            "attached_tool_count": 0,
            "attached_tools": [],
            "thinking": thinking,
            "thinking_level": params.get("thinking_level"),
        }
        if isinstance(extra_metadata, dict):
            metadata.update(extra_metadata)
        updated = store.update_message(
            conversation_id,
            assistant_msg["id"],
            {
                "content": [{"type": "text", "text": current_text}],
                "raw_text": current_text,
                "finish_reason": finish,
                "usage": usage_data if usage_data is not None else {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "metadata": metadata,
                "events": list(assistant_events),
                "tool_logs": [],
                "model": model,
            },
        )
        return updated if updated is not None else assistant_msg

    def append_assistant_event(event):
        assistant_events.append(event)
        return update_assistant_draft()

    def discard_assistant_draft():
        try:
            store.delete_message(conversation_id, assistant_msg["id"])
        except Exception:
            pass

    try:
        if is_cancelled():
            discard_assistant_draft()
            yield from emit_cancelled()
            return

        chain = store.get_message_chain(conversation_id, user_msg["id"])
        standard_messages = convert_to_standard(chain)

        manager = get_manager()
        system_prompt = _conversation_system_prompt(conv, manager)
        user_text = extract_user_text(content)
        inferred_tool_ids = _infer_requested_tools_from_message(user_text)
        input_data = _with_inferred_tools(input_data, inferred_tool_ids)
        if inferred_tool_ids:
            context = dict(context or {})
            context["user_requested_computer_use"] = True
            context = _apply_computer_use_context_preferences(context, user_text)
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
        provider_thinking_parts = []
        finish_reason = "stop"
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        attempts = _ai_retry_attempts(params)
        for attempt_index in range(attempts):
            try:
                chunks = client.stream(model, standard_messages, tools=[], params=params)
                if is_cancelled():
                    discard_assistant_draft()
                    yield from emit_cancelled()
                    return
                if isinstance(chunks, dict) and chunks.get("status") == "error":
                    err = chunks.get("error", {})
                    message_text = err.get("message") if isinstance(err, dict) else err
                    raise RuntimeError(str(message_text or "AI request failed"))
                for chunk in chunks:
                    if is_cancelled():
                        discard_assistant_draft()
                        yield from emit_cancelled()
                        return
                    chunk_type = chunk.get("type", "") if isinstance(chunk, dict) else ""
                    if chunk_type == "content_delta":
                        delta = chunk.get("delta", {})
                        text = delta.get("text", "")
                        if text:
                            visible_text = thought_filter.push(text)
                            thinking_text = thought_filter.pending_thinking_delta()
                            if thinking_text:
                                update_assistant_draft(finish="streaming", thinking_state="streaming")
                                yield {"type": "thinking_delta", "delta": thinking_text}
                            if visible_text:
                                text_parts.append(visible_text)
                                update_assistant_draft(finish="streaming", thinking_state="streaming")
                                yield {"type": "delta", "delta": visible_text}
                    elif chunk_type in {"thinking_delta", "reasoning_delta"}:
                        delta = chunk.get("delta", {}) if isinstance(chunk.get("delta"), dict) else {}
                        text = delta.get("text") or chunk.get("text") or chunk.get("thinking") or chunk.get("reasoning") or ""
                        if text:
                            provider_thinking_parts.append(str(text))
                            update_assistant_draft(finish="streaming", thinking_state="streaming")
                            yield {"type": "thinking_delta", "delta": str(text)}
                    elif chunk_type == "stream_end":
                        finish_reason = chunk.get("finish_reason", "stop")
                        usage = chunk.get("usage", usage)
                break
            except Exception as exc:
                if is_cancelled():
                    discard_assistant_draft()
                    yield from emit_cancelled()
                    return
                message_text = "AI request failed: " + str(exc)
                can_retry = (
                    not "".join(text_parts).strip()
                    and attempt_index < attempts - 1
                    and _is_retryable_ai_error(message_text)
                )
                if can_retry:
                    delay = _ai_retry_delay(params, attempt_index)
                    retry_event = _event(
                        "ai_retry_scheduled",
                        "APIエラーのため少し待って再送信します",
                        phase="ai_retry_scheduled",
                        attempt=attempt_index + 1,
                        max_attempts=attempts,
                        delay_seconds=delay,
                        error=message_text,
                    )
                    append_assistant_event(retry_event)
                    yield retry_event
                    if delay > 0:
                        time.sleep(delay)
                    continue

                failed_response = _ai_error_response(
                    model,
                    message_text,
                    params,
                    events=assistant_events + [
                        _event(
                            "task_failed",
                            "APIエラーでタスクを終了しました",
                            phase="task_failed",
                            error=message_text,
                            terminal=True,
                        )
                    ],
                )
                failed_message = build_assistant_message(
                    conversation_id=conversation_id,
                    parent_id=user_msg["id"],
                    sequence_number=seq,
                    response=failed_response,
                    model=model,
                )
                assistant_msg = store.update_message(conversation_id, assistant_msg["id"], failed_message) or assistant_msg
                yield {
                    "type": "task_failed",
                    "message": "APIエラーでタスクを終了しました",
                    "error": message_text,
                    "terminal": True,
                }
                yield {"type": "message", "message": assistant_msg}
                yield {"type": "done", "message": assistant_msg}
                return

        if is_cancelled():
            discard_assistant_draft()
            yield from emit_cancelled()
            return

        trailing_text = thought_filter.finish()
        thinking_text = thought_filter.pending_thinking_delta()
        if thinking_text:
            update_assistant_draft(finish="streaming", thinking_state="streaming")
            yield {"type": "thinking_delta", "delta": thinking_text}
        if trailing_text:
            text_parts.append(trailing_text)
            update_assistant_draft(finish="streaming", thinking_state="streaming")
            yield {"type": "delta", "delta": trailing_text}

        transcript = current_transcript()
        fallback_response = None
        if not "".join(text_parts).strip():
            if is_cancelled():
                discard_assistant_draft()
                yield from emit_cancelled()
                return
            fallback_response = _fallback_complete_without_thinking(
                client,
                model,
                standard_messages,
                params,
                transcript,
            )
            fallback_text = _text_from_content_blocks(
                fallback_response.get("content") if isinstance(fallback_response, dict) else None
            )
            if fallback_text:
                yield {"type": "delta", "delta": fallback_text}

        if fallback_response is not None:
            response = fallback_response
        else:
            response_text = "".join(text_parts)
            recovered_empty = False
            if not response_text.strip():
                response_text = _empty_stream_message(finish_reason)
                recovered_empty = True
            response = {
                "content": [{"type": "text", "text": response_text}],
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
            if recovered_empty:
                response["metadata"]["empty_stream_response"] = True
        if transcript:
            response["metadata"]["thinking"] = {
                "state": "completed",
                "transcript": transcript,
                "source": "inline_thought_stream",
            }
        existing_events = response.get("events", [])
        response["events"] = list(assistant_events) + (existing_events if isinstance(existing_events, list) else [])
        response["tool_logs"] = response.get("tool_logs", [])

        if is_cancelled():
            discard_assistant_draft()
            yield from emit_cancelled()
            return

        assistant_msg = store.update_message(
            conversation_id,
            assistant_msg["id"],
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
    finally:
        cancel_event.set()
        cancellation_registry.unregister(conversation_id, request_cancel)


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

    message_text = extract_user_text(raw_content)
    inferred_tool_ids = _infer_requested_tools_from_message(message_text)
    input_data = _with_inferred_tools(input_data, inferred_tool_ids)
    if inferred_tool_ids:
        context = dict(context or {})
        context["user_requested_computer_use"] = True
        context = _apply_computer_use_context_preferences(context, message_text)
    tools = input_data.get("tools")
    selected_tools = [item for item in tools if item] if isinstance(tools, list) else []
    client = AIClient()
    model = conv.get("model", "stub/default")
    if selected_tools or not client.supports_stream(model):
        return {"_sse": True, "events": _fallback_send(input_data, context)}
    return {"_sse": True, "events": _stream_response(input_data, context)}
