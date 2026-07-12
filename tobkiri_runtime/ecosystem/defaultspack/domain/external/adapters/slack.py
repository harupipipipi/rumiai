from __future__ import annotations

from typing import Any

from domain.external.response_adapter import ResponseAdapter
from domain.external.token_store import read_external_token
from domain.integrations.http_client import post_json


class SlackResponseAdapter(ResponseAdapter):
    provider = "slack"

    def send(self, plan: dict[str, Any], *, event=None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        if not _external_reply_allowed(plan):
            return {"sent": False, "reason": "external reply suppressed by response prompt policy"}
        channel_id = ""
        thread_ts = ""
        if event is not None:
            metadata = getattr(event, "metadata", {}) if not isinstance(event, dict) else event.get("metadata", {})
            metadata = metadata if isinstance(metadata, dict) else {}
            channel_id = str(metadata.get("channel") or "")
            thread_ts = str(metadata.get("thread_ts") or "")
            scope = getattr(event, "scope", None)
            channel_id = channel_id or str(getattr(scope, "id", "") or "")
        messages = plan.get("messages") if isinstance(plan.get("messages"), list) else []
        results = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            results.append(self.send_channel_message(channel_id, str(message.get("text") or ""), thread_ts=thread_ts))
        return {"sent": any(item.get("sent") for item in results), "results": results}

    def send_channel_message(self, channel_id: str, text: str, *, thread_ts: str = "") -> dict[str, Any]:
        token = read_external_token("slack", kind="bot_token")
        if not token:
            return {"sent": False, "reason": "Slack bot token not configured"}
        if not channel_id or not text:
            return {"sent": False, "reason": "missing channel or text"}
        payload: dict[str, Any] = {"channel": channel_id, "text": text[:39000]}
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


def _external_reply_allowed(plan: dict[str, Any]) -> bool:
    metadata = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
    action_plan = metadata.get("response_action_plan") if isinstance(metadata.get("response_action_plan"), dict) else {}
    if action_plan and not action_plan.get("external_reply", True):
        return False
    decision = metadata.get("response_prompt_decision") if isinstance(metadata.get("response_prompt_decision"), dict) else {}
    if str(decision.get("sensitivity") or "").lower() == "local_only":
        return False
    return True
