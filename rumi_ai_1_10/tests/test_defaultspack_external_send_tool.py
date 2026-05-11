from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.send_tool import external_send_tool  # noqa: E402
from domain.input.envelope import RumiInputEnvelope  # noqa: E402
from domain.input.submit import apply_external_source_context  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402


def test_external_send_tool_dry_run_supports_line_discord_slack_and_web():
    cases = [
        {"provider": "line", "target_id": "U1", "text": "hello", "dry_run": True},
        {"provider": "discord", "channel_id": "C1", "text": "hello", "dry_run": True},
        {"provider": "discord", "webhook_url": "https://discord.com/api/webhooks/x/y", "text": "hello", "dry_run": True},
        {"provider": "slack", "channel_id": "C1", "text": "hello", "dry_run": True},
        {"provider": "web", "callback_url": "https://example.com/hook", "text": "hello", "dry_run": True},
    ]

    for args in cases:
        result = external_send_tool(args, {})
        assert result["is_error"] is False
        assert result["widget"]["dry_run"] is True
        assert result["widget"]["provider"] == args["provider"]


def test_external_send_tool_is_registered_as_approval_gated_output_tool():
    tool = ToolRegistry().get("external_send")

    assert tool is not None
    assert tool["requires_approval"] is True
    assert tool["action_type"] == "write"
    assert "output" in tool["tags"]


def test_source_context_prefix_is_defaultable_without_mutating_envelope_input():
    envelope = RumiInputEnvelope(
        role="user",
        input="hello",
        chat={},
        source={"provider": "line"},
        metadata={
            "external_event": {
                "scope": {"type": "group", "id": "C1"},
                "actor": {"type": "user", "id": "U1"},
            }
        },
        params={
            "external_input": {
                "default_response": {
                    "include_source_context": True,
                    "source_context_format": "${provider}から来た入力です。",
                }
            }
        },
    )

    text = apply_external_source_context("hello", envelope)

    assert envelope.input == "hello"
    assert text.startswith("[External source: lineから来た入力です。")
    assert "scope=group:C1" in text
    assert text.endswith("hello")
