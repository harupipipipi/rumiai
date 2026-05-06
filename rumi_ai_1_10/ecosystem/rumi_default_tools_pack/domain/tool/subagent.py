from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTSPACK_ROOT = _PACK_ROOT.parent / "defaultspack"
for _path in (str(_PACK_ROOT), str(_DEFAULTSPACK_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from domain.ai_client.client import AIClient
from domain.chat.message_builder import build_assistant_message
from domain.chat.store import ChatStore


class SubagentController:
    """Create a child conversation and run a bounded subagent turn."""

    def run(self, arguments: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        context = context or {}
        parent_id = str(context.get("conversation_id") or arguments.get("parent_conversation_id") or "").strip()
        if not parent_id:
            raise ValueError("parent conversation is required for subagent")

        task = str(arguments.get("task") or arguments.get("prompt") or "").strip()
        if not task:
            raise ValueError("'task' is required for subagent")

        store = ChatStore()
        parent = store.get_conversation(parent_id)
        if parent is None:
            raise ValueError("parent conversation not found")

        model = str(arguments.get("model") or context.get("model") or parent.get("model") or "stub/default")
        title = str(arguments.get("title") or task[:48] or "Subagent").strip()
        child = store.create_conversation(
            model=model,
            parent_conversation_id=parent_id,
            conversation_kind="subagent",
            agent_id=str(arguments.get("agent_id") or "subagent"),
            tags=[*list(parent.get("tags", [])), "subagent"],
            metadata={
                "parent_conversation_id": parent_id,
                "subagent": {
                    "task": task,
                    "source": "subagent_tool",
                },
            },
        )
        child = store.update_conversation(child["id"], {"title": title}) or child
        user_msg = store.add_message(
            child["id"],
            {
                "role": "user",
                "content": [{"type": "text", "text": task}],
                "metadata": {"source": "subagent_tool"},
            },
        )
        if user_msg is None:
            raise RuntimeError("failed to write subagent task")

        response = self._complete(model, task)
        assistant = store.add_message(
            child["id"],
            build_assistant_message(
                conversation_id=child["id"],
                parent_id=user_msg["id"],
                sequence_number=user_msg.get("sequence_number", 1) + 1,
                response=response,
                model=model,
            ),
        )
        summary = assistant.get("raw_text") if isinstance(assistant, dict) else response["content"][0]["text"]
        return {
            "action": "subagent.run",
            "parent_conversation_id": parent_id,
            "child_conversation_id": child["id"],
            "title": title,
            "task": task,
            "summary": summary,
        }

    @staticmethod
    def _complete(model: str, task: str) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a focused subagent inside Rumi. Work only on the delegated task, "
                    "be concise, and return a directly useful result."
                ),
            },
            {"role": "user", "content": task},
        ]
        try:
            response = AIClient().complete(model, messages, [], {"max_tokens": 800})
            if isinstance(response, dict):
                return response
        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"Subagent could not complete the task: {exc}"}],
                "finish_reason": "error",
                "usage": {},
                "metadata": {"subagent_error": str(exc)},
            }
        return {
            "content": [{"type": "text", "text": "Subagent finished without a response."}],
            "finish_reason": "stop",
            "usage": {},
        }
