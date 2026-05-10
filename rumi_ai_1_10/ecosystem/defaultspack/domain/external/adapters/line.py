from __future__ import annotations

from typing import Any

from domain.external.response_adapter import ResponseAdapter
from domain.external.token_store import read_external_token
from domain.integrations.http_client import post_json


class LineResponseAdapter(ResponseAdapter):
    provider = "line"

    def send(self, plan: dict[str, Any], *, event=None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        reply_token = ""
        source = {}
        if event is not None:
            metadata = getattr(event, "metadata", {}) if not isinstance(event, dict) else event.get("metadata", {})
            metadata = metadata if isinstance(metadata, dict) else {}
            reply_token = str(metadata.get("reply_token") or "")
            payload = getattr(event, "payload", {}) if not isinstance(event, dict) else event.get("payload", {})
            source = payload.get("source") if isinstance(payload, dict) and isinstance(payload.get("source"), dict) else {}
        messages = plan.get("messages") if isinstance(plan.get("messages"), list) else []
        text = "\n".join(str(message.get("text") or "") for message in messages if isinstance(message, dict)).strip()
        if reply_token:
            return self.send_text_reply(reply_token, text)
        user_id = str(source.get("userId") or "")
        if user_id:
            return self.send_text_push(user_id, text)
        return {"sent": False, "reason": "missing LINE reply token or push target"}

    def send_text_reply(self, reply_token: str, text: str) -> dict[str, Any]:
        token = read_external_token("line", kind="channel_access_token")
        if not token:
            return {"sent": False, "reason": "LINE channel access token not configured"}
        if not reply_token or not text:
            return {"sent": False, "reason": "missing reply token or text"}
        response = post_json(
            "https://api.line.me/v2/bot/message/reply",
            {"Authorization": "Bearer " + token},
            {"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]},
        )
        return {"sent": bool(response.get("ok")), "provider_response": response}

    def send_text_push(self, user_id: str, text: str) -> dict[str, Any]:
        token = read_external_token("line", kind="channel_access_token")
        if not token:
            return {"sent": False, "reason": "LINE channel access token not configured"}
        if not user_id or not text:
            return {"sent": False, "reason": "missing push target or text"}
        response = post_json(
            "https://api.line.me/v2/bot/message/push",
            {"Authorization": "Bearer " + token},
            {"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]},
        )
        return {"sent": bool(response.get("ok")), "provider_response": response}
