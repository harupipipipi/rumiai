from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.adapters import line as line_adapter_module  # noqa: E402
from domain.external.adapters.line import LineResponseAdapter  # noqa: E402
from domain.external.audience_policy import AudiencePolicy  # noqa: E402
from domain.external.audience_policy_registry import AudiencePolicyRegistry  # noqa: E402
from domain.external.normalizer import normalize_line_event  # noqa: E402
from domain.external.source_store import ExternalSourceStore  # noqa: E402
from domain.external.response import RumiResponse  # noqa: E402
from domain.external.response_planner import ResponsePlanner  # noqa: E402
from domain.webhook.endpoint_store import WebhookEndpointStore  # noqa: E402


SECRET = "line-secret"


def _signed_line_payload(payload: dict[str, Any], *, raw_body: bytes | None = None) -> dict[str, Any]:
    raw = raw_body or json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = base64.b64encode(hmac.new(SECRET.encode("utf-8"), raw, hashlib.sha256).digest()).decode("ascii")
    return {
        **payload,
        "_raw_body_base64": base64.b64encode(raw).decode("ascii"),
        "_headers": {"x-line-signature": signature},
    }


def _install_line_endpoint(monkeypatch, tmp_path, *, enabled: bool = True) -> None:
    endpoint_path = tmp_path / "endpoints.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_WEBHOOK_ENDPOINTS_PATH", str(endpoint_path))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_EXTERNAL_SOURCES_PATH", str(tmp_path / "external_sources.json"))
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setenv("LINE_CHANNEL_SECRET", SECRET)
    store = WebhookEndpointStore(endpoint_path)
    store.upsert(
        {
            "id": "line-main",
            "kind": "line",
            "input_profile_id": "line.default",
            "audience_policy_id": "line.production",
            "response_profile_id": "line.default",
            "security": {"mode": "provider_signature"},
            "conversation": {"strategy": "external_key", "model": "stub/default"},
            "enabled": enabled,
        }
    )


def test_line_route_uses_endpoint_enabled_flag(monkeypatch, tmp_path):
    from blocks.integrations import line as line_block  # noqa: E402

    _install_line_endpoint(monkeypatch, tmp_path, enabled=False)
    payload = {"destination": "Udest", "events": []}

    result = line_block.run(_signed_line_payload(payload), {})

    assert result["status"] == "error"
    assert result["_http_status"] == 403


def test_line_route_preserves_top_level_destination_and_endpoint_policy(monkeypatch, tmp_path):
    from blocks.integrations import line as line_block  # noqa: E402

    _install_line_endpoint(monkeypatch, tmp_path, enabled=True)
    captured: dict[str, Any] = {}

    def fake_dispatch(event, *, input_profile_id, audience_policy, context, send_response):
        captured["event"] = event
        captured["input_profile_id"] = input_profile_id
        captured["audience_policy"] = audience_policy
        captured["context"] = context
        captured["send_response"] = send_response
        return {
            "status": "ok",
            "assistant_text": "done",
            "response_plan": {"provider": "line", "messages": [{"type": "text", "text": "done"}]},
        }

    monkeypatch.setattr(line_block, "dispatch_external_event", fake_dispatch)
    monkeypatch.setattr(LineResponseAdapter, "send", lambda self, plan, event=None, context=None: {"sent": True})
    payload = {
        "destination": "Udestination",
        "events": [
            {
                "type": "message",
                "mode": "active",
                "webhookEventId": "evt-1",
                "replyToken": "reply-1",
                "source": {"type": "group", "groupId": "Cgroup", "userId": "Uactor"},
                "message": {"id": "m1", "type": "text", "text": "hello"},
            }
        ],
    }
    raw_body = b'{ "destination" : "Udestination", "events" : [] }'

    result = line_block.run(_signed_line_payload(payload, raw_body=raw_body), {})

    assert result["status"] == "ok"
    assert captured["event"].workspace.id == "Udestination"
    assert captured["input_profile_id"] == "line.default"
    assert captured["context"]["webhook_endpoint"]["id"] == "line-main"
    assert captured["context"]["output_profile_id"] == "line.default"
    assert captured["audience_policy"]["require"] == {"verified": True, "message_types": ["text"]}
    assert captured["audience_policy"]["allow"][0]["scope"] == {"type": "group", "id": "Cgroup"}
    saved = ExternalSourceStore().get("line", "group", "Cgroup")
    assert saved is not None
    assert saved["actor_last_seen"] == "Uactor"
    assert saved["allow_push"] is False


def test_line_route_empty_events_ack_ok_without_dispatch(monkeypatch, tmp_path):
    from blocks.integrations import line as line_block  # noqa: E402

    _install_line_endpoint(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(
        line_block,
        "dispatch_external_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dispatch should not run")),
    )

    result = line_block.run(_signed_line_payload({"destination": "Udest", "events": []}), {})

    assert result["status"] == "ok"
    assert result["data"]["events"] == []


def test_line_default_policy_denies_unknown_source(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_DEFAULTSPACK_EXTERNAL_SOURCES_PATH", str(tmp_path / "external_sources.json"))
    event = normalize_line_event(
        {
            "type": "message",
            "source": {"type": "group", "groupId": "Cunknown", "userId": "Uactor"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
        },
        verified=True,
        destination="Udest",
    )

    policy = AudiencePolicyRegistry().resolve("line.production", event=event)
    decision = AudiencePolicy(policy).evaluate(event)

    assert decision.allowed is False
    assert decision.reason == "default deny"


def test_line_adapter_replies_to_group_origin_without_user_push(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(line_adapter_module, "read_external_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(
        line_adapter_module,
        "post_json",
        lambda url, headers, body: calls.append({"url": url, "body": body}) or {"ok": True},
    )
    event = normalize_line_event(
        {
            "type": "message",
            "replyToken": "reply-group",
            "source": {"type": "group", "groupId": "Cgroup", "userId": "Uactor"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
        },
        verified=True,
    )

    result = LineResponseAdapter().send({"messages": [{"type": "text", "text": "reply"}]}, event=event)

    assert result["sent"] is True
    assert calls[0]["url"].endswith("/message/reply")
    assert calls[0]["body"] == {"replyToken": "reply-group", "messages": [{"type": "text", "text": "reply"}]}


def test_line_adapter_missing_reply_token_does_not_push_actor_user(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(line_adapter_module, "read_external_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(line_adapter_module, "post_json", lambda url, headers, body: calls.append(body) or {"ok": True})
    event = normalize_line_event(
        {
            "type": "message",
            "source": {"type": "group", "groupId": "Cgroup", "userId": "Uactor"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
        },
        verified=True,
    )

    result = LineResponseAdapter().send({"messages": [{"type": "text", "text": "reply"}]}, event=event)

    assert result["sent"] is False
    assert result["reason"] == "missing reply token"
    assert calls == []


def test_line_adapter_push_to_origin_uses_group_and_room_ids(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(line_adapter_module, "read_external_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(
        line_adapter_module,
        "post_json",
        lambda url, headers, body: calls.append({"url": url, "body": body}) or {"ok": True},
    )
    group_event = normalize_line_event(
        {
            "type": "message",
            "source": {"type": "group", "groupId": "Cgroup", "userId": "Uactor"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
        },
        verified=True,
    )
    room_event = normalize_line_event(
        {
            "type": "message",
            "source": {"type": "room", "roomId": "Rroom", "userId": "Uactor"},
            "message": {"id": "m2", "type": "text", "text": "hello"},
        },
        verified=True,
    )

    LineResponseAdapter().send({"messages": [{"type": "text", "text": "group"}]}, event=group_event, context={"send_mode": "push_to_origin", "allow_push": True})
    LineResponseAdapter().send({"messages": [{"type": "text", "text": "room"}]}, event=room_event, context={"send_mode": "push_to_origin", "allow_push": True})

    assert calls[0]["url"].endswith("/message/push")
    assert calls[0]["body"]["to"] == "Cgroup"
    assert calls[1]["body"]["to"] == "Rroom"


def test_line_adapter_standby_does_not_push_by_default(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(line_adapter_module, "read_external_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(line_adapter_module, "post_json", lambda url, headers, body: calls.append(body) or {"ok": True})
    event = normalize_line_event(
        {
            "type": "message",
            "mode": "standby",
            "source": {"type": "group", "groupId": "Cgroup", "userId": "Uactor"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
        },
        verified=True,
    )

    result = LineResponseAdapter().send(
        {"messages": [{"type": "text", "text": "reply"}]},
        event=event,
        context={"send_mode": "push_to_origin", "allow_push": True},
    )

    assert result["sent"] is False
    assert result["reason"] == "push not allowed"
    assert calls == []


def test_line_reply_sends_max_five_messages_without_joining(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(line_adapter_module, "read_external_token", lambda *args, **kwargs: "token")
    monkeypatch.setattr(line_adapter_module, "post_json", lambda url, headers, body: calls.append(body) or {"ok": True})
    event = normalize_line_event(
        {
            "type": "message",
            "replyToken": "reply-user",
            "source": {"type": "user", "userId": "Uuser"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
        },
        verified=True,
    )
    plan = {"messages": [{"type": "text", "text": f"part-{index}"} for index in range(7)]}

    LineResponseAdapter().send(plan, event=event)

    assert [item["text"] for item in calls[0]["messages"]] == ["part-0", "part-1", "part-2", "part-3", "part-4"]


def test_line_planner_limits_messages_to_five():
    plan = ResponsePlanner("line").plan(RumiResponse(text="x" * 26000))

    assert len(plan["messages"]) == 5
    assert plan["fallbacks"][0]["reason"] == "text message count limit exceeded"


def test_line_image_message_marked_as_unsupported_attachment():
    event = normalize_line_event(
        {
            "type": "message",
            "source": {"type": "user", "userId": "Uuser"},
            "message": {"id": "m-image", "type": "image"},
        },
        verified=True,
    )

    assert event.metadata["attachments"] == [
        {
            "provider": "line",
            "message_id": "m-image",
            "message_type": "image",
            "content_api": "https://api-data.line.me/v2/bot/message/m-image/content",
            "retrieval": "line_content_api",
            "status": "unsupported_inline",
        }
    ]
