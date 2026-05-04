from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any, Dict

from blocks._common import ok, error
from blocks.integrations.common import headers_from_request, raw_body_bytes, text_limit
from domain.integrations.chat_bridge import dispatch_external_message
from domain.integrations.http_client import post_json
from domain.integrations.secrets import load_integration_secrets_into_env


def run(input_data, context):
    load_integration_secrets_into_env()
    headers = headers_from_request(input_data)
    raw_body = raw_body_bytes(input_data)
    verification = _verify_line(headers, raw_body)
    if not verification["ok"]:
        return {**error(verification["reason"], "SIGNATURE_INVALID"), "_http_status": 401}

    events = input_data.get("events") if isinstance(input_data.get("events"), list) else []
    results = []
    for event in events:
        if not isinstance(event, dict):
            continue
        result = _handle_event(
            event,
            context,
            model=input_data.get("model") if isinstance(input_data.get("model"), str) else None,
            tools=input_data.get("tools") if isinstance(input_data.get("tools"), list) else None,
            params=input_data.get("params") if isinstance(input_data.get("params"), dict) else None,
        )
        results.append(result)
    return ok({"verified": verification["verified"], "events": results})


def _handle_event(
    event: Dict[str, Any],
    context,
    *,
    model: str | None = None,
    tools=None,
    params=None,
) -> Dict[str, Any]:
    if event.get("type") != "message":
        return {"ignored": True, "reason": "unsupported LINE event", "event_type": event.get("type")}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    message_type = message.get("type")
    if message_type == "text":
        text = str(message.get("text") or "").strip()
    else:
        text = "LINE {} message received. messageId={}".format(message_type or "unknown", message.get("id", ""))
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    source_id = str(source.get("groupId") or source.get("roomId") or source.get("userId") or "unknown-source")
    external_key = "|".join(["line", str(source.get("type") or "chat"), source_id])
    result = dispatch_external_message(
        provider="line",
        text=text,
        external_key=external_key,
        title="LINE " + source_id,
        event_id=str(event.get("webhookEventId") or message.get("id") or ""),
        metadata={
            "source": source,
            "reply_token": event.get("replyToken"),
            "message_id": message.get("id"),
            "message_type": message_type,
        },
        model=model,
        tools=tools,
        params=params,
        context=context,
    )
    reply = _send_line_reply(str(event.get("replyToken") or ""), result.get("assistant_text", ""))
    return {**result, "reply": reply}


def _verify_line(headers: Dict[str, str], raw_body: bytes) -> Dict[str, Any]:
    secret = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
    if not secret:
        return {"ok": True, "verified": False, "reason": "no channel secret configured"}
    signature = headers.get("x-line-signature", "")
    if not signature:
        return {"ok": False, "verified": False, "reason": "missing LINE signature header"}
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    if not hmac.compare_digest(expected, signature):
        return {"ok": False, "verified": False, "reason": "LINE signature mismatch"}
    return {"ok": True, "verified": True, "reason": ""}


def _send_line_reply(reply_token: str, text: str) -> Dict[str, Any]:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        return {"sent": False, "reason": "LINE_CHANNEL_ACCESS_TOKEN not configured"}
    if not reply_token or not text:
        return {"sent": False, "reason": "missing reply token or text"}
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text_limit(text, 5000)}],
    }
    response = post_json(
        "https://api.line.me/v2/bot/message/reply",
        {"Authorization": "Bearer " + token},
        payload,
    )
    return {"sent": bool(response.get("ok")), "provider_response": response}
