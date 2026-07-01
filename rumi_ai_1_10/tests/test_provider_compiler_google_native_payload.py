from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "provider_payloads"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _assert_google_native_tool_history_valid(contents):
    pending = []

    def _matches(call, response):
        call_id = str(call.get("id") or "")
        response_id = str(response.get("id") or "")
        if call_id and response_id:
            return call_id == response_id
        return str(call.get("name") or "") == str(response.get("name") or "")

    for item in contents:
        parts = item.get("parts") or []
        calls = [part["functionCall"] for part in parts if isinstance(part, dict) and isinstance(part.get("functionCall"), dict)]
        responses = [part["functionResponse"] for part in parts if isinstance(part, dict) and isinstance(part.get("functionResponse"), dict)]
        if pending and not responses:
            raise AssertionError("model functionCall was not immediately answered by functionResponse")
        if responses:
            if not pending:
                raise AssertionError("functionResponse has no preceding model functionCall")
            for response in responses:
                for index, call in enumerate(pending):
                    if _matches(call, response):
                        pending.pop(index)
                        break
                else:
                    raise AssertionError("functionResponse does not match pending functionCall")
        if calls:
            if pending:
                raise AssertionError("new functionCall started before prior call was answered")
            pending = list(calls)

    if pending:
        raise AssertionError("model functionCall was left without a functionResponse")


def test_google_native_compiler_matches_text_image_tool_snapshot():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.google_native import GoogleNativeCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir(
            [
                {"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}]},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "tc", "function": {"name": "lookup", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "tc", "name": "lookup", "content": "{\"ok\":true}"},
            ],
            "c",
        ),
        model="gemma-4-31b-it",
        provider_capabilities={"provider_id": "google", "api_family": "google_native"},
        provider_tools=[{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
    )

    body = GoogleNativeCompiler().compile_complete(planned).body
    assert body == json.loads((FIXTURES / "google_native_text_image_tool.json").read_text())
    _assert_google_native_tool_history_valid(body["contents"])


def test_google_native_compiler_prunes_orphan_tool_call_before_approval_followup():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.google_native import GoogleNativeCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir(
            [
                {"role": "user", "content": "Inspect the workspace and report back."},
                {
                    "role": "assistant",
                    "content": "I need to run a terminal command.",
                    "tool_calls": [
                        {
                            "id": "call-terminal-approval",
                            "type": "function",
                            "function": {"name": "terminal_exec", "arguments": "{\"command\":\"pytest\"}"},
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": "Approval required before terminal execution can continue.",
                    "metadata": {"status": "approval_required"},
                },
                {
                    "role": "user",
                    "content": [],
                    "metadata": {"scheduled_task_message": "Scheduler follow-up after approval."},
                },
                {"role": "user", "content": "Run the next Gemma QA pass."},
            ],
            "conv-mimo",
        ),
        model="gemma-4-31b-it",
        provider_capabilities={"provider_id": "google", "api_family": "google_native"},
        provider_tools=[{"type": "function", "function": {"name": "terminal_exec", "parameters": {"type": "object"}}}],
    )

    body = GoogleNativeCompiler().compile_complete(planned).body
    parts = [part for item in body["contents"] for part in item.get("parts") or []]

    assert not any("functionCall" in part for part in parts)
    assert not any("functionResponse" in part for part in parts)
    assert "I need to run a terminal command." in [part.get("text") for part in parts]
    assert "Approval required before terminal execution can continue." in [part.get("text") for part in parts]
    assert "Scheduler follow-up after approval." in [part.get("text") for part in parts]
    _assert_google_native_tool_history_valid(body["contents"])


def test_google_native_parser_handles_multiple_parts():
    from domain.ai_client.provider_compiler.google_native import GoogleNativeCompiler
    from domain.ai_client.provider_compiler.base import CompiledProviderRequest

    parsed = GoogleNativeCompiler().parse_response(
        {"candidates": [{"content": {"parts": [{"text": "visible"}, {"text": "thought", "thought": True}, {"functionCall": {"id": "tc", "name": "lookup", "args": {"q": "x"}}}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2, "totalTokenCount": 3}},
        CompiledProviderRequest(api_family="google_native", provider_id="google", model="m", path="", metadata={}),
    )

    assert parsed.content[0].text == "visible"
    assert parsed.content[1].tool_call.name == "lookup"
    assert parsed.metadata["thinking"]["transcript"] == "thought"


def test_google_native_compiler_normalizes_gemma_thinking_level():
    from domain.ai_client.bridge_plan import PlannedProviderRequest
    from domain.ai_client.provider_compiler.google_native import GoogleNativeCompiler
    from domain.chat.ir_legacy_adapter import legacy_standard_messages_to_ir

    compiler = GoogleNativeCompiler()
    planned = PlannedProviderRequest(
        ir=legacy_standard_messages_to_ir([{"role": "user", "content": "qa"}], "c"),
        model="gemma-4-31b-it",
        provider_capabilities={"provider_id": "google", "api_family": "google_native"},
        provider_tools=[],
        params={"thinking_level": "none"},
    )

    body = compiler.compile_complete(planned).body

    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "MINIMAL"
