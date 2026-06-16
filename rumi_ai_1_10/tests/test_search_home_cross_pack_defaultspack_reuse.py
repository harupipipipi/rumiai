from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
                "data": {
                    "status": "ok",
                    "output": {
                        "route": "ASK_AI_WITH_SEARCH",
                        "confidence": 0.94,
                        "normalized_query": args["question"].split("User input:\n", 1)[-1],
                        "target_url": None,
                        "reason": "fresh information needed",
                    },
                },
            }
        if qualified_name == "defaultspack.chat.create_conversation":
            return {"status": "ok", "data": {"id": "conv_search_home"}}
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
                    "tool_logs": [{"tool_name": "web_search"}],
                },
            }
        raise AssertionError(f"Unexpected function call: {qualified_name}")


def test_search_home_classifier_uses_defaultspack_model_call():
    runtime = FakeRuntime()
    bridge = DefaultspackBridge(invoker=runtime.invoke)

    bridge.classify_with_ai("日東紡 株価")

    assert runtime.calls[0]["qualified_name"] == "defaultspack.ai.model_call"


def test_search_home_ask_with_search_uses_defaultspack_chat_pipeline_and_web_search():
    runtime = FakeRuntime()
    bridge = DefaultspackBridge(invoker=runtime.invoke)

    result = bridge.ask_ai("日東紡 株価", with_search=True)

    assert "defaultspack.chat.create_conversation" in runtime.call_names
    assert "defaultspack.chat.send" in runtime.call_names
    assert runtime.last_chat_payload is not None
    assert runtime.last_chat_payload["params"]["tool_policy"]["selected_tools"] == ["web_search"]
    assert runtime.last_chat_payload["params"]["tool_policy"]["allowed_tools"] == ["web_search"]
    assert result["used_tools"] == ["web_search"]


def test_search_home_ask_without_search_skips_tool_policy():
    runtime = FakeRuntime()
    bridge = DefaultspackBridge(invoker=runtime.invoke)

    bridge.ask_ai("Go fmtって必要？", with_search=False)

    assert runtime.last_chat_payload is not None
    assert runtime.last_chat_payload["params"] == {}
