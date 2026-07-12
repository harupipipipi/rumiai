from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.send_tool import external_send_tool  # noqa: E402
from domain.input.envelope import RumiInputEnvelope  # noqa: E402
from domain.input.submit import apply_external_runtime_prompt, apply_external_source_context  # noqa: E402
from domain.tool.registry import ToolRegistry  # noqa: E402


def test_external_send_tool_dry_run_supports_line_discord_slack_and_web():
    cases = [
        {"provider": "line", "target_id": "U1", "text": "hello", "dry_run": True},
        {"provider": "discord", "channel_id": "C1", "text": "hello", "dry_run": True},
        {
            "provider": "discord",
            "webhook_url": "https://discord.com/api/webhooks/x/y",
            "text": "hello",
            "dry_run": True,
        },
        {"provider": "slack", "channel_id": "C1", "text": "hello", "dry_run": True},
        {
            "provider": "web",
            "callback_url": "https://example.com/hook",
            "text": "hello",
            "dry_run": True,
        },
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


def test_runtime_prompt_prefix_and_suffix_wrap_external_text():
    text = apply_external_runtime_prompt(
        "hello",
        {
            "external_prompt_prefix": "Use computer_use in Google Chrome.",
            "external_prompt_suffix": "Return only a short local confirmation.",
        },
    )

    assert text.startswith("Use computer_use in Google Chrome.")
    assert "\n\nhello\n\n" in text
    assert text.endswith("Return only a short local confirmation.")


def test_external_send_blocks_private_loopback_webhook_urls():
    cases = [
        {"provider": "web", "callback_url": "http://127.0.0.1:8080/private", "text": "hello"},
        {"provider": "generic", "callback_url": "https://127.0.0.1/private", "text": "hello"},
        {"provider": "discord", "webhook_url": "https://127.0.0.1/private", "text": "hello"},
    ]

    for args in cases:
        result = external_send_tool(args, {})
        assert result["is_error"] is False
        assert result["widget"]["sent"] is False
        assert "internal_secret" not in str(result["widget"].get("provider_response", {}))


def test_discord_webhook_url_must_target_discord_host():
    result = external_send_tool(
        {
            "provider": "discord",
            "webhook_url": "https://example.com/api/webhooks/id/token",
            "text": "hello",
        },
        {},
    )

    assert result["is_error"] is False
    assert result["widget"]["sent"] is False
    assert (
        result["widget"]["provider_response"]["body"]["error"] == "webhook URL host is not allowed"
    )


def test_public_webhook_helper_suppresses_response_body(monkeypatch):
    from domain.integrations import http_client

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"internal_secret":"IMDS-LOCAL-SECRET"}'

    class FakeOpener:
        def open(self, request, timeout=10.0):
            return FakeResponse()

    monkeypatch.setattr(
        http_client.socket,
        "getaddrinfo",
        lambda host, port, type=0: [
            (
                http_client.socket.AF_INET,
                http_client.socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", port),
            )
        ],
    )
    monkeypatch.setattr(http_client.urllib.request, "build_opener", lambda *handlers: FakeOpener())

    result = http_client.post_json_public_url("https://example.com/hook", {}, {"text": "hello"})

    assert result == {"ok": True, "status": 200, "body": {}}
