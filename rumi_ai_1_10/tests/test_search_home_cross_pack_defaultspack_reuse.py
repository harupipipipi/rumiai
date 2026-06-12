from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
for candidate in (ROOT, DEFAULTSPACK_ROOT):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from ecosystem.search_home_pack.domain.defaultspack_bridge import DefaultspackBridge  # noqa: E402


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.last_chat_payload: dict[str, Any] | None = None

    @property
    def call_names(self) -> list[str]:
        return [str(call["qualified_name"]) for call in self.calls]

    def invoke(
        self,
        qualified_name: str,
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "qualified_name": qualified_name,
                "args": args,
                "context": context or {},
                "timeout_seconds": timeout_seconds,
            }
        )
        if qualified_name == "defaultspack.ai.model_call":
            return {
                "status": "ok",
                "model": args.get("model") or "stub/default",
                "output": {
                    "best_index": 0,
                    "confidence": 0.94,
                    "reason": "fresh information needed",
                    "ordered_indexes": [0],
                    "reject_reasons": {},
                },
            }
        if qualified_name == "defaultspack.chat.create_conversation":
            return {"id": "conv_search_home"}
        if qualified_name == "defaultspack.chat.send":
            self.last_chat_payload = args
            return {
                "status": "ok",
                "data": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Current answer"}],
                    "raw_text": "Current answer",
                    "model": "stub/default",
                    "metadata": {
                        "model_routing": {"selected_model": "stub/default"},
                    },
                    "tool_logs": [{"tool_name": "web_search"}] if args.get("tools") else [],
                },
            }
        raise AssertionError(f"Unexpected function call: {qualified_name}")


class RuntimeChatStore:
    def __init__(self, runtime: FakeRuntime) -> None:
        self._runtime = runtime

    def create_conversation(self, **kwargs):
        return self._runtime.invoke("defaultspack.chat.create_conversation", kwargs)


def test_search_home_target_judge_uses_defaultspack_model_call():
    runtime = FakeRuntime()
    bridge = DefaultspackBridge(
        call_model_fn=lambda payload, context=None: runtime.invoke("defaultspack.ai.model_call", payload, context),
        model_caps_fn=lambda _model: {"supports_image_input": False, "supports_vision": False},
    )

    result = bridge.judge_search_targets(
        "日東紡 株価",
        [
            {
                "url": "https://example.com/stock",
                "final_url": "https://example.com/stock",
                "title": "Stock information",
                "domain": "example.com",
            }
        ],
    )

    assert result["status"] == "ok"
    assert runtime.calls[0]["qualified_name"] == "defaultspack.ai.model_call"


def test_search_home_answer_with_search_uses_defaultspack_chat_pipeline_and_web_search():
    runtime = FakeRuntime()
    bridge = DefaultspackBridge(
        chat_send_fn=lambda payload, context=None: runtime.invoke("defaultspack.chat.send", payload, context),
        chat_store_factory=lambda: RuntimeChatStore(runtime),
    )

    result = bridge.answer_query("日東紡 株価", use_search=True)

    assert "defaultspack.chat.create_conversation" in runtime.call_names
    assert "defaultspack.chat.send" in runtime.call_names
    assert runtime.last_chat_payload is not None
    assert runtime.last_chat_payload["tools"] == ["web_search"]
    assert runtime.last_chat_payload["params"]["tool_policy"]["selected_tools"] == ["web_search"]
    assert result["used_tools"] == ["web_search"]


def test_search_home_answer_without_search_sends_empty_tool_selection():
    runtime = FakeRuntime()
    bridge = DefaultspackBridge(
        chat_send_fn=lambda payload, context=None: runtime.invoke("defaultspack.chat.send", payload, context),
        chat_store_factory=lambda: RuntimeChatStore(runtime),
    )

    bridge.answer_query("Go fmtって必要？", use_search=False)

    assert runtime.last_chat_payload is not None
    assert runtime.last_chat_payload["tools"] == []
    assert runtime.last_chat_payload["params"]["tool_policy"]["selected_tools"] == []
