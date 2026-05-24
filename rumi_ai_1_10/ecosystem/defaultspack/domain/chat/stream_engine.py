from __future__ import annotations

import threading
import time
from typing import Any, Iterator

from blocks._common import gen_id, timestamp
from blocks.chat.send import (
    _ai_error_after_tool_use_response,
    _ai_error_response,
    _ai_retry_attempts,
    _ai_retry_delay,
    _append_assistant_tool_use_message,
    _append_tool_result_message,
    _bounded_compact_tool_result,
    _compact_tool_log_value,
    _empty_response_message,
    _is_retryable_ai_error,
    _params_without_thinking,
    _redact_sensitive_value,
    _tool_blocked_response,
    _tool_limit_message,
    _tool_result_artifacts,
    _tool_result_is_error,
    _tool_result_recovery_kind,
    _tool_result_summary,
    _tool_use_blocks,
    _tool_visibility_message,
)
from domain.ai_client.client import AIClient
from domain.ai_client.gateway import LLMGateway
from domain.chat.cancellation import get_chat_cancellation_registry
from domain.chat.message_builder import build_assistant_message
from domain.chat.run_request import PreparedChatRun, prepare_chat_run
from domain.chat.tool_call_accumulator import ToolCallAccumulator
from domain.chat.store import ChatStore
from domain.dev.inspector import Inspector
from domain.stream.events import run_event, to_legacy_chat_stream_event
from domain.tool.executor import ToolExecutor
from domain.tool.schema_adapter import build_tool_execution_context, max_tool_calls, tool_name_from_definition


class _ChatCancelled(Exception):
    pass


_APPROVAL_WAITING_TEXT = "許可が必要なため、ユーザーが承認するまで待機します。承認後に続行します。"


def _tool_display_group(tool_name: str) -> dict[str, str]:
    lowered = str(tool_name or "").lower()
    rules = [
        (("calculator", "calc", "math"), "calculation", "計算"),
        (("web", "search", "reddit"), "web/search", "Web検索"),
        (("browser", "computer"), "browser", "ブラウザ"),
        (("todo", "task"), "planning/todo", "Todo"),
        (("delegate", "subagent", "agent"), "agent/delegation", "Delegation"),
        (("terminal", "shell", "exec"), "coding/terminal", "ターミナル"),
        (("file", "read", "write", "list"), "coding/files", "ファイル"),
        (("git", "branch", "commit", "diff"), "coding/git", "Git"),
    ]
    for keys, group_id, label in rules:
        if any(key in lowered for key in keys):
            return {"id": group_id, "label": label}
    return {"id": "tools", "label": "Tools"}


def _display_arg(arguments: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
    return ""


def _tool_display_action(tool_name: str, arguments: dict[str, Any]) -> str:
    lowered = str(tool_name or "").lower()
    if not isinstance(arguments, dict):
        arguments = {}
    if "calculator" in lowered or "calc" in lowered:
        return _display_arg(arguments, ("expression", "expr", "input", "query"))
    if "search" in lowered or "web" in lowered or "reddit" in lowered:
        query = _display_arg(arguments, ("query", "q", "search_query", "text", "url"))
        return "検索: {}".format(query) if query else "検索"
    if "file" in lowered:
        path = _display_arg(arguments, ("path", "filename", "directory", "glob"))
        return "ファイル確認: {}".format(path) if path else "ファイル確認"
    if "browser" in lowered or "computer" in lowered:
        action = _display_arg(arguments, ("action",)) or "画面操作"
        target = _display_arg(arguments, ("url", "app", "application", "browser", "name", "title"))
        text = _display_arg(arguments, ("text", "key"))
        return " ".join(part for part in (action, target, text) if part).strip()
    if "terminal" in lowered or "shell" in lowered or "exec" in lowered:
        command = _display_arg(arguments, ("command", "cmd"))
        return "コマンド実行: {}".format(command) if command else "コマンド実行"
    if "todo" in lowered:
        return _display_arg(arguments, ("title", "task", "action", "todo_id")) or "Todo更新"
    if "delegate" in lowered or "subagent" in lowered or "agent" in lowered:
        return _display_arg(arguments, ("task", "title", "prompt")) or "委任実行"
    return ""


def _tool_display_payload(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    status: str,
    summary: str = "",
) -> dict[str, Any]:
    group = _tool_display_group(tool_name)
    action = _tool_display_action(tool_name, arguments)
    if status == "running":
        display_text = "{}を進めています".format(action or tool_name or "tool")
        next_step = "結果が届き次第、次の判断に使います。"
    elif status == "failed":
        display_text = summary or "{} が失敗しました".format(tool_name or "tool")
        next_step = "失敗理由を確認して、必要なら止まります。"
    else:
        display_text = summary or "{} が完了しました".format(tool_name or "tool")
        next_step = "結果をもとに次の応答へ進みます。"
    return {
        "display_text": display_text,
        "status": status,
        "group": group,
        "action": action,
        "next_step": next_step,
    }


def _should_emit_model_routing_status(model_routing: dict[str, Any] | None) -> bool:
    if not isinstance(model_routing, dict) or not model_routing:
        return False
    if model_routing.get("bridge_required") or model_routing.get("warnings"):
        return True
    selected = str(model_routing.get("selected_model") or "")
    original = str(model_routing.get("original_model") or "")
    return bool(selected and original and selected != original)


def _approval_request_from_tool_result(
    tool_name: str,
    tool_call_id: str,
    arguments: dict[str, Any],
    result: Any,
) -> dict[str, Any] | None:
    roots: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(value: Any) -> None:
        if not isinstance(value, dict):
            return
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
        roots.append(value)

    add(result)
    if isinstance(result, dict):
        data = result.get("data")
        add(data)
        if isinstance(data, dict):
            nested_data = data.get("data")
            add(nested_data)
            if isinstance(nested_data, dict):
                add(nested_data.get("widget"))
                add(nested_data.get("result"))
            add(data.get("widget"))
            add(data.get("result"))
        add(result.get("widget"))
        for key in ("result", "output", "artifact", "capture"):
            add(result.get(key))

    for root in roots:
        requires_approval = bool(root.get("requires_approval") or root.get("approval_required"))
        if not requires_approval:
            continue
        payload = root.get("payload")
        if not isinstance(payload, dict):
            payload = root.get("arguments") if isinstance(root.get("arguments"), dict) else arguments
        action = str(root.get("action") or arguments.get("action") or tool_name).strip()
        return {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "action": action,
            "payload": dict(payload or {}),
            "requires_approval": True,
            "approval_required": True,
            "approval_token": root.get("approval_token"),
            "approval_request_id": root.get("approval_request_id") or root.get("request_id"),
            "risk_level": root.get("risk_level"),
            "expires_at": root.get("expires_at"),
            "approval_expires_in_seconds": root.get("approval_expires_in_seconds"),
            "display_summary": root.get("display_summary"),
            "message": root.get("message") or root.get("approval_hint") or _APPROVAL_WAITING_TEXT,
        }
    return None


def _response_reasoning_content(response: dict[str, Any] | None) -> str:
    if not isinstance(response, dict):
        return ""
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value
    metadata = response.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("reasoning_content")
        if isinstance(value, str) and value.strip():
            return value
        thinking = metadata.get("thinking")
        if isinstance(thinking, dict):
            transcript = thinking.get("transcript")
            if isinstance(transcript, str) and transcript.strip():
                return transcript
    return ""


def _default_tool_limit_for_connected_tools(tool_limit: int, connected_tool_names: set[str]) -> int:
    if tool_limit != 4:
        return tool_limit
    if connected_tool_names.intersection({"browser_companion", "browser_computer", "browser_use", "computer_use"}):
        return 12
    if any(str(name or "").startswith("coding_") for name in connected_tool_names):
        return 12
    return tool_limit


def _approval_waiting_response(
    model: str,
    approval_request: dict[str, Any],
    params: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": _APPROVAL_WAITING_TEXT}],
        "finish_reason": "approval_required",
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "metadata": {
            "model": model,
            "pending_approval": approval_request,
            "thinking_level": params.get("thinking_level"),
        },
        "events": list(events),
    }


class _InlineThoughtFilter:
    _open_tag = "<thought>"
    _close_tag = "</thought>"

    def __init__(self) -> None:
        self._buffer = ""
        self._in_thought = False
        self._thought_parts: list[str] = []
        self._streamed_thought_len = 0

    def push(self, text: Any) -> str:
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

    def finish(self) -> str:
        visible = ""
        if self._buffer:
            if self._in_thought:
                self._thought_parts.append(self._buffer)
            else:
                visible = self._buffer
        self._buffer = ""
        return visible

    def pending_thinking_delta(self) -> str:
        transcript = "".join(self._thought_parts)
        delta = transcript[self._streamed_thought_len:]
        self._streamed_thought_len = len(transcript)
        return delta

    def transcript(self) -> str:
        return "".join(self._thought_parts).strip()

    @classmethod
    def _partial_open_tag_suffix_len(cls, text: str) -> int:
        max_len = min(len(text), len(cls._open_tag) - 1)
        for size in range(max_len, 0, -1):
            if cls._open_tag.startswith(text[-size:]):
                return size
        return 0


class _AssistantDraft:
    _min_sync_interval_seconds = 0.15

    def __init__(
        self,
        *,
        store: ChatStore,
        conversation_id: str,
        parent_id: str,
        sequence_number: int,
        model: str,
        params: dict[str, Any],
    ) -> None:
        self._store = store
        self._conversation_id = conversation_id
        self._model = model
        self._params = params
        self._last_sync_at = 0.0
        self._last_signature: tuple[Any, ...] | None = None
        self.message = store.add_message(
            conversation_id,
            {
                "role": "assistant",
                "parent_id": parent_id,
                "sequence_number": sequence_number,
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
                    "thinking_level": params.get("thinking_level"),
                },
                "events": [],
                "tool_logs": [],
                "model": model,
            },
        )

    @property
    def id(self) -> str:
        return str((self.message or {}).get("id") or "")

    def update(
        self,
        *,
        content_text: str,
        thinking_transcript: str,
        events: list[dict[str, Any]],
        tool_logs: list[dict[str, Any]],
        finish_reason: str = "streaming",
        thinking_state: str = "running",
        usage: dict[str, Any] | None = None,
        metadata_extra: dict[str, Any] | None = None,
        force: bool = False,
    ) -> None:
        if not self.message:
            return
        signature = self._signature(
            content_text=content_text,
            thinking_transcript=thinking_transcript,
            events=events,
            tool_logs=tool_logs,
            finish_reason=finish_reason,
            thinking_state=thinking_state,
            usage=usage,
            metadata_extra=metadata_extra,
        )
        now = time.monotonic()
        if signature == self._last_signature:
            return
        if not force and self._last_sync_at and (now - self._last_sync_at) < self._min_sync_interval_seconds:
            return
        metadata = {
            "model": self._model,
            "streaming": True,
            "draft": True,
            "thinking": {"state": thinking_state},
            "thinking_level": self._params.get("thinking_level"),
        }
        if thinking_transcript:
            metadata["thinking"]["transcript"] = thinking_transcript
        if isinstance(metadata_extra, dict):
            metadata.update(metadata_extra)
        updated = self._store.update_message(
            self._conversation_id,
            self.id,
            {
                "content": [{"type": "text", "text": content_text}],
                "raw_text": content_text,
                "finish_reason": finish_reason,
                "usage": usage if usage is not None else {},
                "metadata": metadata,
                "events": list(events),
                "tool_logs": list(tool_logs),
                "model": self._model,
            },
        )
        if updated is not None:
            self.message = updated
            self._last_signature = signature
            self._last_sync_at = now

    def finalize(self, assistant_message: dict[str, Any]) -> dict[str, Any] | None:
        if not self.message:
            return assistant_message
        updates = dict(assistant_message)
        metadata = dict(updates.get("metadata") or {})
        metadata.pop("streaming", None)
        metadata.pop("draft", None)
        updates["metadata"] = metadata
        return self._store.update_message(self._conversation_id, self.id, updates)

    def cancel(
        self,
        *,
        content_text: str,
        thinking_transcript: str,
        events: list[dict[str, Any]],
        tool_logs: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not self.message:
            return None
        final_text = content_text if content_text.strip() else "停止しました。"
        metadata = {
            "model": self._model,
            "thinking": {"state": "cancelled"},
            "thinking_level": self._params.get("thinking_level"),
            "cancelled": True,
        }
        if thinking_transcript:
            metadata["thinking"]["transcript"] = thinking_transcript
        updated = self._store.update_message(
            self._conversation_id,
            self.id,
            {
                "content": [{"type": "text", "text": final_text}],
                "raw_text": final_text,
                "finish_reason": "cancelled",
                "usage": {},
                "metadata": metadata,
                "events": list(events),
                "tool_logs": list(tool_logs),
                "model": self._model,
            },
        )
        if updated is not None:
            self.message = updated
        return updated

    def discard(self) -> None:
        if not self.message:
            return
        try:
            self._store.delete_message(self._conversation_id, self.id)
        except Exception:
            pass

    @staticmethod
    def _signature(
        *,
        content_text: str,
        thinking_transcript: str,
        events: list[dict[str, Any]],
        tool_logs: list[dict[str, Any]],
        finish_reason: str,
        thinking_state: str,
        usage: dict[str, Any] | None,
        metadata_extra: dict[str, Any] | None,
    ) -> tuple[Any, ...]:
        last_event = events[-1] if events else None
        last_tool_log = tool_logs[-1] if tool_logs else None
        usage_items = tuple(sorted((usage or {}).items())) if isinstance(usage, dict) else ()
        metadata_items = tuple(sorted((metadata_extra or {}).items())) if isinstance(metadata_extra, dict) else ()
        return (
            content_text,
            thinking_transcript,
            finish_reason,
            thinking_state,
            len(events),
            repr(last_event),
            len(tool_logs),
            repr(last_tool_log),
            usage_items,
            metadata_items,
        )


class ChatRunEngine:
    def __init__(
        self,
        *,
        store: ChatStore | None = None,
        client: AIClient | None = None,
        gateway: LLMGateway | None = None,
    ) -> None:
        self._store = store or ChatStore()
        self._gateway = gateway or LLMGateway(client=client)
        self._run_id = ""
        self._conversation_id = ""
        self._event_seq = 0
        self._cancel_event = threading.Event()
        self._current_stream: Any = None
        self._activity_events: list[dict[str, Any]] = []
        self._tool_logs: list[dict[str, Any]] = []
        self._thinking_transcript_parts: list[str] = []
        self._text_parts: list[str] = []
        self._started_tool_call_ids: set[str] = set()
        self._browser_state_revision = 0
        self._stream_mode = True

    def stream(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
        *,
        stream_mode: bool = True,
    ) -> Iterator[dict[str, Any]]:
        prepared = prepare_chat_run(input_data, context)
        self._run_id = gen_id()
        self._conversation_id = prepared.conversation_id
        self._event_seq = 0
        self._activity_events = []
        self._tool_logs = []
        self._thinking_transcript_parts = []
        self._text_parts = []
        self._started_tool_call_ids = set()
        self._browser_state_revision = 0
        self._stream_mode = bool(stream_mode)
        self._cancel_event = threading.Event()
        self._current_stream = None

        cancellation_registry = get_chat_cancellation_registry()

        def request_cancel() -> None:
            self._cancel_event.set()
            close = getattr(self._current_stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

        draft: _AssistantDraft | None = None
        cancellation_registry.register(prepared.conversation_id, request_cancel)
        try:
            yield self._emit(
                "run_started",
                data={
                    "model": prepared.model,
                    "request_id": prepared.request_id,
                    "stream_mode": stream_mode,
                    "model_routing": prepared.model_routing,
                    "chat_references": dict(prepared.chat_references or {}),
                },
                message="chat run started",
            )
            if _should_emit_model_routing_status(prepared.model_routing):
                yield self._emit(
                    "status",
                    data=prepared.model_routing,
                    message="model routing prepared",
                    phase="model_routing",
                    model=prepared.model,
                )
            yield self._emit(
                "user_message_committed",
                data={"message": prepared.user_message},
                message="user message committed",
            )

            assistant_seq = int(prepared.user_message.get("sequence_number", 1) or 1) + 1
            if stream_mode:
                draft = _AssistantDraft(
                    store=self._store,
                    conversation_id=prepared.conversation_id,
                    parent_id=str(prepared.user_message["id"]),
                    sequence_number=assistant_seq,
                    model=prepared.model,
                    params=prepared.params,
                )
                if draft.message is not None:
                    yield self._emit(
                        "assistant_message_started",
                        data={"message": draft.message},
                        message="assistant draft created",
                    )

            if prepared.provider_tools:
                yield self._emit(
                    "status",
                    data={"model": prepared.model},
                    message="{} が考えています".format(prepared.model),
                    phase="thinking",
                    model=prepared.model,
                )
                yield self._emit(
                    "status",
                    data={"tool_count": len(prepared.provider_tools)},
                    message="{} 個の tool を接続しました".format(len(prepared.provider_tools)),
                    phase="tools_attached",
                )
            self._sync_draft(draft, force=True)

            try:
                self._raise_if_cancelled()
                try:
                    from domain.chat.run_request import prefocus_computer_use_target_window

                    prefocus_computer_use_target_window(prepared)
                except Exception:
                    pass
                response = yield from self._execute(prepared, draft)
            except _ChatCancelled:
                cancelled_event = self._emit(
                    "cancelled",
                    data={"reason": "cancelled"},
                    message="cancelled",
                    reason="cancelled",
                )
                if draft is not None:
                    draft.cancel(
                        content_text="".join(self._text_parts),
                        thinking_transcript="".join(self._thinking_transcript_parts),
                        events=list(self._activity_events),
                        tool_logs=list(self._tool_logs),
                    )
                yield cancelled_event
                return
            except RuntimeError as exc:
                task_failed_event = self._emit(
                    "task_failed",
                    data={"error": str(exc), "terminal": True},
                    message="APIエラーでタスクを終了しました",
                    phase="task_failed",
                    error=str(exc),
                    terminal=True,
                )
                yield task_failed_event
                response = _ai_error_response(
                    prepared.model,
                    str(exc),
                    prepared.params,
                    events=list(self._activity_events),
                )
            except Exception as exc:
                message_text = "AI request failed: " + str(exc)
                task_failed_event = self._emit(
                    "task_failed",
                    data={"error": message_text, "terminal": True},
                    message="APIエラーでタスクを終了しました",
                    phase="task_failed",
                    error=message_text,
                    terminal=True,
                )
                yield task_failed_event
                response = _ai_error_response(
                    prepared.model,
                    message_text,
                    prepared.params,
                    events=list(self._activity_events),
                )

            finalized_response = self._final_response(prepared, response)
            self._log_inspector(prepared, finalized_response)
            assistant_message = build_assistant_message(
                conversation_id=prepared.conversation_id,
                parent_id=prepared.user_message["id"],
                sequence_number=assistant_seq,
                response=finalized_response,
                model=prepared.model,
            )
            if draft is not None:
                stored = draft.finalize(assistant_message)
            else:
                stored = self._store.add_message(prepared.conversation_id, assistant_message)
            if stored is None:
                yield self._emit(
                    "error",
                    data={"error": {"message": "Failed to add assistant message"}},
                    message="Failed to add assistant message",
                )
                return

            yield self._emit(
                "assistant_message_completed",
                data={"message": stored},
                message="assistant message completed",
            )
            steer_processed = self._process_conversation_steer(prepared.conversation_id, context or {})
            if steer_processed:
                yield self._emit(
                    "status",
                    data={"processed": steer_processed},
                    message="次の steer を送信しました",
                    phase="conversation_steer",
                )
            yield self._emit(
                "done",
                data={"message": stored},
                message="done",
            )
        finally:
            self._cancel_event.set()
            cancellation_registry.unregister(prepared.conversation_id, request_cancel)

    def _process_conversation_steer(self, conversation_id: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            from domain.chat.steer import ConversationSteerStore

            return ConversationSteerStore().process_for_conversation(
                conversation_id,
                context=context,
            )
        except Exception as exc:
            self._emit(
                "status",
                data={"error": str(exc)},
                message="conversation steer の処理に失敗しました",
                phase="conversation_steer_failed",
            )
            return []

    def _execute(self, prepared: PreparedChatRun, draft: _AssistantDraft | None) -> Iterator[dict[str, Any]]:
        working_messages = list(prepared.standard_messages)
        tool_context_message = _tool_visibility_message(prepared.provider_tools)
        if tool_context_message is not None:
            insert_at = 1 if working_messages and working_messages[0].get("role") == "system" else 0
            working_messages.insert(insert_at, tool_context_message)

        response = None
        blocked_response = None
        tool_limit = max_tool_calls(prepared.tool_context or {})
        if tool_limit is None:
            tool_limit = int(prepared.params.get("max_tool_calls", 4) or 4)
        tool_limit = _default_tool_limit_for_connected_tools(tool_limit, prepared.connected_tool_names)

        for step_index in range(max(1, tool_limit + 1)):
            self._raise_if_cancelled()
            for event in self._inject_conversation_steer(prepared.conversation_id, working_messages):
                yield event
            response, tool_uses = yield from self._model_turn(prepared, working_messages, draft)
            if tool_uses and step_index >= tool_limit:
                response = {
                    "content": [{"type": "text", "text": _tool_limit_message(tool_limit, tool_uses)}],
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
                yield self._emit(
                    "status",
                    data={"tool_count": len(self._tool_logs), "max_tool_calls": tool_limit},
                    message="tool call の上限に達したため停止しました",
                    phase="tool_call_limit",
                )
                self._sync_draft(draft, force=True)
                break
            if not tool_uses:
                break

            _append_assistant_tool_use_message(
                working_messages,
                tool_uses,
                reasoning_content=_response_reasoning_content(response),
            )
            for block in tool_uses:
                self._raise_if_cancelled()
                tool_name = str(block.get("name") or block.get("tool_name") or "").strip()
                if not tool_name:
                    continue
                tool_call_id = str(block.get("id") or block.get("tool_call_id") or gen_id()).strip()
                arguments = self._tool_arguments(block)
                if tool_call_id not in self._started_tool_call_ids:
                    self._started_tool_call_ids.add(tool_call_id)
                    display_payload = _tool_display_payload(tool_name, arguments, status="running")
                    event = self._emit(
                        "tool_call_started",
                        data={"tool_name": tool_name, "tool_call_id": tool_call_id, "arguments": arguments, **display_payload},
                        message=display_payload["display_text"],
                        phase="tool_call_started",
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        arguments=arguments,
                    )
                    self._sync_draft(draft, force=True)
                    yield event
                for event in self._before_tool_call(prepared, tool_name, tool_call_id, arguments):
                    yield event
                result = self._execute_tool(prepared, tool_name, tool_call_id, arguments)
                self._raise_if_cancelled()
                summary = _tool_result_summary(tool_name, result)
                artifacts = _tool_result_artifacts(result)
                status = "failed" if _tool_result_is_error(result) else "completed"
                display_payload = _tool_display_payload(tool_name, arguments, status=status, summary=summary)
                for event in self._after_tool_call(prepared, tool_name, tool_call_id, arguments, result):
                    yield event
                completed_event = self._emit(
                    "tool_call_completed",
                    data={
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "is_error": _tool_result_is_error(result),
                        "recovery_kind": _tool_result_recovery_kind(result),
                        "result_summary": summary,
                        "summary": summary,
                        **display_payload,
                        "result": _bounded_compact_tool_result(result, summary, artifacts),
                        "artifacts": artifacts,
                        "artifact_paths": [artifact.get("path") for artifact in artifacts if artifact.get("path")],
                    },
                    message=display_payload["display_text"],
                    phase="tool_call_completed",
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    is_error=_tool_result_is_error(result),
                )
                self._sync_draft(draft, force=True)
                yield completed_event
                approval_request = _approval_request_from_tool_result(tool_name, tool_call_id, arguments, result)
                if approval_request is not None:
                    approval_event = self._emit(
                        "approval_requested",
                        data=approval_request,
                        message=_APPROVAL_WAITING_TEXT,
                        phase="approval_requested",
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        requires_approval=True,
                    )
                    self._sync_draft(draft, force=True)
                    yield approval_event
                    blocked_response = _approval_waiting_response(
                        prepared.model,
                        approval_request,
                        prepared.params,
                        events=list(self._activity_events),
                    )
                    break
                _append_tool_result_message(working_messages, tool_name, result, tool_call_id, model=prepared.model)

                recovery_kind = _tool_result_recovery_kind(result)
                if recovery_kind in {"visible_window_required", "focus_required"}:
                    blocked_response = _tool_blocked_response(tool_name, result)
                    yield self._emit(
                        "status",
                        data={"tool_name": tool_name, "tool_call_id": tool_call_id, "recovery_kind": recovery_kind},
                        message="可視画面外の tool 実行要求のため停止しました",
                        phase="tool_blocked",
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                    )
                    break
            if blocked_response is not None:
                response = blocked_response
                break

        return response or _ai_error_response(
            prepared.model,
            "AI provider did not return a response",
            prepared.params,
            events=list(self._activity_events),
        )

    def _inject_conversation_steer(self, conversation_id: str, working_messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        try:
            from domain.chat.steer import ConversationSteerStore

            items = ConversationSteerStore().consume_for_conversation(conversation_id)
        except Exception as exc:
            yield self._emit(
                "status",
                data={"error": str(exc)},
                message="conversation steer の取得に失敗しました",
                phase="conversation_steer_failed",
            )
            return
        prompts = [str(item.get("prompt") or "").strip() for item in items if isinstance(item, dict) and str(item.get("prompt") or "").strip()]
        if not prompts:
            return
        working_messages.append(
            {
                "role": "user",
                "content": "[RUNTIME INSTRUCTION - User steering while the task is running]\n" + "\n\n".join(prompts),
            }
        )
        yield self._emit(
            "status",
            data={"processed": items},
            message="ステアを次の判断に反映しました",
            phase="conversation_steer",
        )

    def _model_turn(
        self,
        prepared: PreparedChatRun,
        messages: list[dict[str, Any]],
        draft: _AssistantDraft | None,
    ) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
        if not self._stream_mode:
            response = self._complete_turn(prepared, messages)
            return response, _tool_use_blocks(response)
        if prepared.provider_tools and not self._provider_supports_stream_tool_calls(prepared.model):
            response = self._complete_turn(prepared, messages)
            tool_uses = _tool_use_blocks(response)
            if not tool_uses:
                text = self._response_text(response)
                if text:
                    self._text_parts.append(text)
                    yield self._emit("content_delta", data={"delta": text}, message="content delta")
                    self._sync_draft(draft, thinking_state="completed")
            return response, tool_uses

        if not self._gateway.supports_stream(prepared.model):
            response = self._complete_turn(prepared, messages)
            tool_uses = _tool_use_blocks(response)
            if not tool_uses:
                text = self._response_text(response)
                if text:
                    self._text_parts.append(text)
                    yield self._emit("content_delta", data={"delta": text}, message="content delta")
                    self._sync_draft(draft, thinking_state="completed")
            return response, tool_uses

        thought_filter = _InlineThoughtFilter()
        accumulator = ToolCallAccumulator()
        finish_reason = "stop"
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        attempts = _ai_retry_attempts(prepared.params)
        for attempt_index in range(attempts):
            try:
                self._current_stream = self._gateway.stream(
                    {
                        "model": prepared.model,
                        "messages": messages,
                        "tools": prepared.provider_tools,
                        "params": prepared.params,
                    }
                )
                self._raise_if_cancelled()
                for chunk in self._current_stream:
                    self._raise_if_cancelled()
                    if not isinstance(chunk, dict):
                        continue
                    chunk_type = str(chunk.get("type") or "").strip()
                    if chunk_type == "content_delta":
                        delta = chunk.get("delta", {}) if isinstance(chunk.get("delta"), dict) else {}
                        text = delta.get("text", "")
                        if text:
                            visible_text = thought_filter.push(text)
                            thinking_text = thought_filter.pending_thinking_delta()
                            if thinking_text:
                                self._thinking_transcript_parts.append(str(thinking_text))
                                yield self._emit("thinking_delta", data={"delta": str(thinking_text)}, message="thinking delta")
                            if visible_text:
                                self._text_parts.append(str(visible_text))
                                yield self._emit("content_delta", data={"delta": str(visible_text)}, message="content delta")
                            self._sync_draft(draft, thinking_state="streaming")
                    elif chunk_type in {"thinking_delta", "reasoning_delta"}:
                        delta = chunk.get("delta", {}) if isinstance(chunk.get("delta"), dict) else {}
                        text = delta.get("text") or chunk.get("text") or chunk.get("thinking") or chunk.get("reasoning") or ""
                        if text:
                            self._thinking_transcript_parts.append(str(text))
                            yield self._emit("thinking_delta", data={"delta": str(text)}, message="thinking delta")
                            self._sync_draft(draft, thinking_state="streaming")
                    elif chunk_type in {"tool_call_start", "tool_call_delta", "tool_call_end", "tool_use"}:
                        accumulator.ingest(chunk)
                        call_id = str(chunk.get("id") or chunk.get("tool_call_id") or "").strip()
                        tool_name = str(chunk.get("name") or chunk.get("tool_name") or "").strip()
                        if chunk_type == "tool_call_start" and call_id and call_id not in self._started_tool_call_ids:
                            self._started_tool_call_ids.add(call_id)
                            display_payload = _tool_display_payload(tool_name or "tool", {}, status="running")
                            event = self._emit(
                                "tool_call_started",
                                data={"tool_name": tool_name, "tool_call_id": call_id, **display_payload},
                                message=display_payload["display_text"],
                                phase="tool_call_started",
                                tool_name=tool_name,
                                tool_call_id=call_id,
                            )
                            self._sync_draft(draft, thinking_state="streaming", force=True)
                            yield event
                        if chunk_type == "tool_call_delta":
                            arguments_chunk = str(chunk.get("arguments_chunk") or "")
                            event = self._emit(
                                "tool_call_delta",
                                data={
                                    "tool_name": tool_name,
                                    "tool_call_id": call_id,
                                    "arguments_chunk": arguments_chunk,
                                    "status": "running",
                                    "display_text": "{} の入力を受け取っています".format(tool_name or "tool"),
                                },
                                message="{} の入力を受け取っています".format(tool_name or "tool"),
                                phase="tool_call_delta",
                                tool_name=tool_name,
                                tool_call_id=call_id,
                            )
                            self._sync_draft(draft, thinking_state="streaming", force=True)
                            yield event
                    elif chunk_type == "stream_end":
                        finish_reason = str(chunk.get("finish_reason") or "stop")
                        usage = chunk.get("usage", usage) if isinstance(chunk.get("usage"), dict) else usage
                break
            except Exception as exc:
                self._raise_if_cancelled()
                message_text = "AI request failed: " + str(exc)
                can_retry = (
                    not "".join(self._text_parts).strip()
                    and attempt_index < attempts - 1
                    and _is_retryable_ai_error(message_text)
                )
                if can_retry:
                    delay = _ai_retry_delay(prepared.params, attempt_index)
                    yield self._emit(
                        "ai_retry_scheduled",
                        data={
                            "attempt": attempt_index + 1,
                            "max_attempts": attempts,
                            "delay_seconds": delay,
                            "error": message_text,
                        },
                        message="APIエラーのため少し待って再送信します",
                        phase="ai_retry_scheduled",
                    )
                    self._sync_draft(draft, thinking_state="running", force=True)
                    if delay > 0:
                        time.sleep(delay)
                    continue
                if self._tool_logs:
                    response = _ai_error_after_tool_use_response(message_text)
                    response["tool_logs"] = list(self._tool_logs)
                    response["events"] = list(self._activity_events)
                    return response, []
                raise RuntimeError(message_text)
            finally:
                self._current_stream = None

        trailing_text = thought_filter.finish()
        thinking_text = thought_filter.pending_thinking_delta()
        if thinking_text:
            self._thinking_transcript_parts.append(str(thinking_text))
            yield self._emit("thinking_delta", data={"delta": str(thinking_text)}, message="thinking delta")
        if trailing_text:
            self._text_parts.append(str(trailing_text))
            yield self._emit("content_delta", data={"delta": str(trailing_text)}, message="content delta")
        self._sync_draft(draft, thinking_state="streaming")

        tool_uses = accumulator.tool_uses()
        response_text = "".join(self._text_parts)
        if not response_text.strip() and not tool_uses:
            fallback_response = self._fallback_complete_without_thinking(
                prepared,
                messages,
                transcript="".join(self._thinking_transcript_parts),
            )
            fallback_tool_uses = _tool_use_blocks(fallback_response) if isinstance(fallback_response, dict) else []
            if fallback_tool_uses:
                tool_uses = fallback_tool_uses
            fallback_text = self._text_from_content_blocks(
                fallback_response.get("content") if isinstance(fallback_response, dict) else None
            )
            if fallback_text:
                self._text_parts.append(fallback_text)
                yield self._emit("content_delta", data={"delta": fallback_text}, message="content delta")
                response_text = "".join(self._text_parts)
            response = fallback_response
        else:
            response = None

        if response is None:
            if not response_text.strip() and not tool_uses:
                response_text = _empty_response_message(finish_reason)
            response = {
                "content": [{"type": "text", "text": response_text}],
                "finish_reason": finish_reason,
                "usage": usage,
                "metadata": {},
            }
        return response, tool_uses

    def _complete_turn(self, prepared: PreparedChatRun, messages: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            response = self._call_ai_complete_with_retry(
                prepared.model,
                messages,
                prepared.provider_tools,
                prepared.params,
                prepared.call_handler,
                allow_retry=True,
            )
        except RuntimeError as exc:
            if self._tool_logs:
                response = _ai_error_after_tool_use_response(str(exc))
                response["tool_logs"] = list(self._tool_logs)
                response["events"] = list(self._activity_events)
                return response
            raise
        if not isinstance(response, dict):
            response = _ai_error_response(
                prepared.model,
                "AI provider returned an invalid response",
                prepared.params,
                events=list(self._activity_events),
            )
        if not _tool_use_blocks(response) and not self._response_text(response).strip():
            retry_params = _params_without_thinking(prepared.params)
            if retry_params != prepared.params:
                retry_response = self._call_ai_complete_with_retry(
                    prepared.model,
                    messages,
                    prepared.provider_tools,
                    retry_params,
                    prepared.call_handler,
                    allow_retry=False,
                )
                if isinstance(retry_response, dict) and (
                    self._response_text(retry_response).strip() or _tool_use_blocks(retry_response)
                ):
                    metadata = dict(retry_response.get("metadata") or {})
                    metadata["recovered_from_empty_response"] = True
                    retry_response["metadata"] = metadata
                    response = retry_response
        return response

    def _execute_tool(
        self,
        prepared: PreparedChatRun,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        invoke_context = build_tool_execution_context(prepared.tool_context or {}, tool_name, prepared.connected_tool_names)
        invoke_context = dict(invoke_context or {})
        invoke_context["run_event_sink"] = self._legacy_tool_event_sink
        invoke_context["run_id"] = self._run_id
        invoke_context["tool_call_id"] = tool_call_id
        invoke_context["is_cancelled"] = self._is_cancelled
        invoke_context["stream_event_callback"] = self._legacy_stream_event_callback
        if prepared.call_handler is not None:
            result = prepared.call_handler(
                "defaults.tool.invoke",
                {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "context": invoke_context,
                },
            )
        else:
            executed = ToolExecutor().execute(tool_name, arguments, invoke_context)
            result = {"status": "ok", "data": executed}

        log = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "arguments": _redact_sensitive_value(arguments),
            "result": _compact_tool_log_value(result),
            "timestamp": timestamp(),
        }
        self._tool_logs.append(log)
        return result

    def _final_response(self, prepared: PreparedChatRun, response: dict[str, Any]) -> dict[str, Any]:
        finalized = dict(response or _ai_error_response(
            prepared.model,
            "AI provider did not return a final response",
            prepared.params,
            events=list(self._activity_events),
        ))
        if not _tool_use_blocks(finalized) and not self._response_text(finalized).strip():
            finalized["content"] = [{"type": "text", "text": _empty_response_message(finalized.get("finish_reason"))}]
            metadata = dict(finalized.get("metadata") or {})
            metadata["empty_ai_response"] = True
            finalized["metadata"] = metadata
        metadata = dict(finalized.get("metadata") or {})
        requested_tools = list(prepared.tools_called or [])
        attached_provider_tools = [
            name
            for name in (tool_name_from_definition(tool) for tool in prepared.provider_tools)
            if name
        ]
        executed_tools: list[str] = []
        for log in self._tool_logs:
            tool_name = str(log.get("tool_name") or "").strip()
            if tool_name and tool_name not in executed_tools:
                executed_tools.append(tool_name)
        model_warnings: list[str] = []
        if isinstance(prepared.model_routing, dict) and isinstance(prepared.model_routing.get("warnings"), list):
            model_warnings = [str(item) for item in prepared.model_routing.get("warnings", [])]
        metadata.update(
            {
                "model": prepared.model,
                "attached_tool_count": len(prepared.provider_tools),
                "requested_tools": requested_tools,
                "attached_tools": attached_provider_tools,
                "attached_provider_tools": attached_provider_tools,
                "executed_tools": executed_tools,
                "thinking": {
                    "state": "completed" if finalized.get("finish_reason") != "error" else "failed",
                    **({"transcript": "".join(self._thinking_transcript_parts)} if self._thinking_transcript_parts else {}),
                },
                "thinking_level": prepared.params.get("thinking_level"),
                "model_routing": dict(prepared.model_routing or {}),
                "chat_references": dict(prepared.chat_references or {}),
            }
        )
        if "selected_model_does_not_support_tool_calling" in model_warnings:
            metadata["tool_calling_unverified"] = True
            metadata["tool_calling_unavailable_reason"] = "selected_model_does_not_support_tool_calling"
        if prepared.matched_skills:
            metadata["matched_skill_instructions"] = list(prepared.matched_skills)
        finalized["metadata"] = metadata
        finalized["events"] = list(self._activity_events)
        finalized["tool_logs"] = list(self._tool_logs)
        return finalized

    def _sync_draft(self, draft: _AssistantDraft | None, *, thinking_state: str = "running", force: bool = False) -> None:
        if draft is None:
            return
        draft.update(
            content_text="".join(self._text_parts),
            thinking_transcript="".join(self._thinking_transcript_parts),
            events=self._activity_events,
            tool_logs=self._tool_logs,
            finish_reason="streaming",
            thinking_state=thinking_state,
            force=force,
        )

    def _emit(
        self,
        event_type: str,
        *,
        data: dict[str, Any] | None = None,
        message: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        self._event_seq += 1
        event = run_event(
            event_type,
            run_id=self._run_id,
            conversation_id=self._conversation_id,
            seq=self._event_seq,
            data=data,
            timestamp=timestamp(),
            message=message,
            **extra,
        )
        legacy = to_legacy_chat_stream_event(event)
        if legacy is not None and self._is_activity_event(legacy):
            self._activity_events.append(legacy)
        return event

    @staticmethod
    def _is_activity_event(event: dict[str, Any]) -> bool:
        event_type = str(event.get("type") or "").strip()
        return event_type in {
            "status",
            "tool_call_started",
            "tool_call_delta",
            "tool_call_completed",
            "browser_state_invalidated",
            "browser_state_snapshot",
            "browser_dom_snapshot",
            "browser_screenshot",
            "approval_requested",
            "ai_retry_scheduled",
            "task_failed",
            "cancelled",
        }

    def _provider_supports_stream_tool_calls(self, model: str) -> bool:
        try:
            provider, _ = self._gateway.resolve_provider(model)
        except Exception:
            return False
        name = provider.__class__.__name__.lower()
        return name in {"openaiprovider", "googleprovider"}

    def _log_inspector(self, prepared: PreparedChatRun, response: dict[str, Any]) -> None:
        try:
            source = "domain.chat.stream_engine"
            if isinstance(prepared.request_context, dict):
                source = str(
                    prepared.request_context.get("run_source")
                    or prepared.request_context.get("source")
                    or source
                )
            enrich_info = prepared.enrich_info if isinstance(prepared.enrich_info, dict) else {}
            executed_tool_names = [
                str(log.get("tool_name") or "").strip()
                for log in self._tool_logs
                if isinstance(log, dict) and str(log.get("tool_name") or "").strip()
            ]
            unknown_selected_tools = []
            if isinstance(prepared.tool_context, dict):
                raw_unknown = prepared.tool_context.get("unknown_selected_tools")
                if isinstance(raw_unknown, list):
                    unknown_selected_tools = [str(item) for item in raw_unknown if str(item or "").strip()]
            metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
            usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
            Inspector().log_request(
                request_id=prepared.request_id,
                conversation_id=prepared.conversation_id,
                model=prepared.model,
                prompt_used=str(enrich_info.get("enriched_prompt") or prepared.system_prompt or ""),
                tools_called=executed_tool_names or list(prepared.tools_called),
                context_info={
                    "source": source,
                    "run_id": self._run_id,
                    "stream_mode": self._stream_mode,
                    "message_count": len(prepared.standard_messages),
                    "params": dict(prepared.params or {}),
                    "attached_tools": list(prepared.tools_called),
                    "executed_tools": executed_tool_names,
                    "unknown_selected_tools": unknown_selected_tools,
                    "knowledge_results": enrich_info.get("knowledge_results", []),
                    "memory_results": enrich_info.get("memory_results", []),
                    "chat_references": dict(prepared.chat_references or {}),
                    "matched_skill_instructions": list(prepared.matched_skills or []),
                    "finish_reason": response.get("finish_reason"),
                    "usage": usage,
                    "metadata": metadata,
                },
            )
        except Exception:
            pass

    def _call_ai_complete_with_retry(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        params: dict[str, Any],
        call_handler: Any,
        *,
        allow_retry: bool,
    ) -> dict[str, Any]:
        attempts = _ai_retry_attempts(params) if allow_retry else 1
        last_error = "AI request failed"
        for attempt_index in range(attempts):
            try:
                if call_handler is not None:
                    response = call_handler(
                        "defaults.ai.complete",
                        {
                            "model": model,
                            "messages": messages,
                            "tools": tools,
                            "params": params,
                        },
                    )
                    if isinstance(response, dict) and response.get("status") == "error":
                        err = response.get("error", {})
                        raise RuntimeError(str(err.get("message") or "AI request failed"))
                    if isinstance(response, dict) and response.get("status") == "ok":
                        return response.get("data", {})
                    return response
                return self._gateway.complete(
                    {"model": model, "messages": messages, "tools": tools or [], "params": params or {}}
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt_index >= attempts - 1 or not _is_retryable_ai_error(last_error):
                    break
                delay = _ai_retry_delay(params, attempt_index)
                self._activity_events.append(
                    {
                        "type": "ai_retry_scheduled",
                        "message": "APIエラーのため少し待って再送信します",
                        "phase": "ai_retry_scheduled",
                        "attempt": attempt_index + 1,
                        "max_attempts": attempts,
                        "delay_seconds": delay,
                        "error": last_error,
                        "timestamp": timestamp(),
                    }
                )
                if delay > 0:
                    time.sleep(delay)
        raise RuntimeError(last_error)

    def _before_tool_call(
        self,
        prepared: PreparedChatRun,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return []

    def _after_tool_call(
        self,
        prepared: PreparedChatRun,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            from domain.chat.browser_state import emit_browser_state_events
        except Exception:
            return []
        action = ""
        if isinstance(arguments, dict):
            action = str(arguments.get("action") or "").strip()
        emission = emit_browser_state_events(
            tool_name,
            result,
            tool_call_id=tool_call_id,
            action=action,
            timestamp=timestamp(),
            state_revision=self._browser_state_revision,
        )
        self._browser_state_revision = max(self._browser_state_revision, int(emission.state_revision or 0))
        normalized = []
        for item in emission.events or []:
            event = self._normalize_browser_state_event(item)
            if event is not None:
                normalized.append(event)
        return normalized

    def _normalize_browser_state_event(self, event: Any) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            return None
        kind = str(event.get("event") or "").strip()
        mapping = {
            "invalidated": ("browser_state_invalidated", "invalidated"),
            "snapshot": ("browser_state_snapshot", "snapshot"),
            "dom_snapshot": ("browser_dom_snapshot", "dom_snapshot"),
            "screenshot": ("browser_screenshot", "screenshot"),
        }
        if kind not in mapping:
            return self._normalize_external_event(event)
        canonical_type, payload_key = mapping[kind]
        payload = event.get(payload_key) if isinstance(event.get(payload_key), dict) else {}
        data = {payload_key: payload, **payload}
        if event.get("timestamp") is not None and "timestamp" not in data:
            data["timestamp"] = event.get("timestamp")
        message_text = str(event.get("message") or payload.get("message") or canonical_type)
        extras = {
            key: value
            for key, value in event.items()
            if key
            not in {
                "type",
                "event",
                payload_key,
                "timestamp",
                "message",
                "data",
                "schema_version",
                "run_id",
                "conversation_id",
                "seq",
            }
        }
        normalized = self._emit(
            canonical_type,
            data=data,
            message=message_text,
            **extras,
        )
        return normalized

    def _normalize_external_event(self, event: Any) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            return None
        event_type = str(event.get("type") or "").strip()
        if not event_type:
            return None
        if event.get("schema_version") == 1:
            legacy = to_legacy_chat_stream_event(event)
            if legacy is not None and self._is_activity_event(legacy):
                self._activity_events.append(legacy)
            return event
        payload = dict(event.get("data") or {})
        for key, value in event.items():
            if key == "type":
                continue
            payload.setdefault(key, value)
        normalized = self._emit(event_type, data=payload, message=str(payload.get("message") or event_type))
        return normalized

    def _legacy_tool_event_sink(self, event: dict[str, Any]) -> None:
        normalized = self._normalize_external_event(event)
        if normalized is not None:
            legacy = to_legacy_chat_stream_event(normalized)
            if legacy is not None and self._is_activity_event(legacy) and legacy not in self._activity_events:
                self._activity_events.append(legacy)

    def _legacy_stream_event_callback(self, event: dict[str, Any]) -> None:
        self._legacy_tool_event_sink(event)

    def _is_cancelled(self) -> bool:
        return self._cancel_event.is_set() or get_chat_cancellation_registry().is_cancelled(self._conversation_id)

    def _raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise _ChatCancelled()

    @staticmethod
    def _tool_arguments(block: dict[str, Any]) -> dict[str, Any]:
        value = block.get("input", block.get("arguments", {}))
        if isinstance(value, str):
            try:
                parsed = __import__("json").loads(value)
            except Exception:
                return {"value": value}
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _response_text(response: dict[str, Any]) -> str:
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

    @staticmethod
    def _text_from_content_blocks(content: Any) -> str:
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

    def _fallback_complete_without_thinking(
        self,
        prepared: PreparedChatRun,
        messages: list[dict[str, Any]],
        *,
        transcript: str = "",
    ) -> dict[str, Any] | None:
        fallback_tool_sets: list[list[dict[str, Any]]] = []
        if prepared.provider_tools:
            fallback_tool_sets.append(prepared.provider_tools)
        fallback_tool_sets.append([])
        for tools in fallback_tool_sets:
            try:
                response = self._gateway.complete(
                    {
                        "model": prepared.model,
                        "messages": messages,
                        "tools": tools,
                        "params": _params_without_thinking(prepared.params),
                    }
                )
            except Exception:
                continue
            if not isinstance(response, dict):
                continue
            if not self._text_from_content_blocks(response.get("content")) and not _tool_use_blocks(response):
                continue
            metadata = dict(response.get("metadata") or {})
            if transcript:
                metadata["thinking"] = {"state": "completed", "transcript": transcript}
            else:
                metadata.setdefault("thinking", {"state": "completed"})
            metadata["recovered_from_empty_stream"] = True
            metadata["fallback_kept_tools"] = bool(tools)
            metadata.setdefault("model", prepared.model)
            metadata.setdefault("attached_tool_count", len(prepared.provider_tools))
            metadata.setdefault("attached_tools", list(prepared.tools_called))
            metadata["thinking_level"] = prepared.params.get("thinking_level")
            response["metadata"] = metadata
            return response
        return None
