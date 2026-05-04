from __future__ import annotations

import hmac
import hashlib
import time
from typing import Any, Dict

from blocks._common import ok, error
from blocks.integrations.common import allow_unsigned_webhook_dev, headers_from_request, raw_body_bytes, text_limit
from domain.integrations.chat_bridge import dispatch_external_message
from domain.integrations.http_client import post_json
from domain.integrations.secrets import get_integration_secret, load_integration_secrets_into_env


def run(input_data, context):
    load_integration_secrets_into_env()
    headers = headers_from_request(input_data)
    raw_body = raw_body_bytes(input_data)
    verification = _verify_slack(headers, raw_body)
    if not verification["ok"]:
        return {**error(verification["reason"], "SIGNATURE_INVALID"), "_http_status": 401}

    if input_data.get("type") == "url_verification":
        return {"challenge": input_data.get("challenge", "")}

    if input_data.get("type") != "event_callback":
        return ok({"ignored": True, "reason": "unsupported slack payload"})

    event = input_data.get("event") if isinstance(input_data.get("event"), dict) else {}
    if event.get("subtype") == "bot_message" or event.get("bot_id"):
        return ok({"ignored": True, "reason": "bot message"})
    if event.get("type") not in {"message", "app_mention"}:
        return ok({"ignored": True, "reason": "unsupported slack event"})

    text = str(event.get("text") or "").strip()
    if not text:
        return ok({"ignored": True, "reason": "empty slack message"})

    team_id = str(input_data.get("team_id") or event.get("team") or "unknown-team")
    channel = str(event.get("channel") or "")
    user = str(event.get("user") or "")
    thread_ts = str(event.get("thread_ts") or event.get("ts") or "")
    external_key = "|".join(["slack", team_id, channel, thread_ts or user or "direct"])
    result = dispatch_external_message(
        provider="slack",
        text=text,
        external_key=external_key,
        title="Slack " + (channel or user or "chat"),
        event_id=str(input_data.get("event_id") or event.get("client_msg_id") or event.get("ts") or ""),
        model=str(input_data.get("model") or "") or None,
        metadata={
            "team_id": team_id,
            "channel": channel,
            "user": user,
            "thread_ts": thread_ts,
            "event_ts": event.get("event_ts") or event.get("ts"),
        },
        context=context,
    )
    reply = result.get("assistant_text", "")
    send_result = _send_slack_reply(channel, reply, thread_ts)
    return ok({**result, "verified": verification["verified"], "reply": send_result})


def _verify_slack(headers: Dict[str, str], raw_body: bytes) -> Dict[str, Any]:
    secret = get_integration_secret("slack", "SLACK_SIGNING_SECRET")
    if not secret:
        if allow_unsigned_webhook_dev():
            return {"ok": True, "verified": False, "reason": "unsigned dev mode enabled"}
        return {"ok": False, "verified": False, "reason": "Slack signing secret not configured"}
    timestamp = headers.get("x-slack-request-timestamp", "")
    signature = headers.get("x-slack-signature", "")
    if not timestamp or not signature:
        return {"ok": False, "verified": False, "reason": "missing Slack signature headers"}
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return {"ok": False, "verified": False, "reason": "stale Slack signature timestamp"}
    except ValueError:
        return {"ok": False, "verified": False, "reason": "invalid Slack signature timestamp"}
    base = b"v0:" + timestamp.encode("utf-8") + b":" + raw_body
    expected = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return {"ok": False, "verified": False, "reason": "Slack signature mismatch"}
    return {"ok": True, "verified": True, "reason": ""}


def _send_slack_reply(channel: str, text: str, thread_ts: str = "") -> Dict[str, Any]:
    token = get_integration_secret("slack", "SLACK_BOT_TOKEN")
    if not token:
        return {"sent": False, "reason": "SLACK_BOT_TOKEN not configured"}
    if not channel or not text:
        return {"sent": False, "reason": "missing channel or text"}
    payload: Dict[str, Any] = {"channel": channel, "text": text_limit(text, 39000)}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    response = post_json(
        "https://slack.com/api/chat.postMessage",
        {"Authorization": "Bearer " + token},
        payload,
    )
    body = response.get("body") if isinstance(response, dict) else {}
    return {
        "sent": bool(response.get("ok")) and (not isinstance(body, dict) or body.get("ok") is not False),
        "provider_response": response,
    }
