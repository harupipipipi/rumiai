from __future__ import annotations

from typing import Any

from domain.external.response_adapter import ResponseAdapter
from domain.external.token_store import read_external_token
from domain.integrations.http_client import post_json


class DiscordResponseAdapter(ResponseAdapter):
    provider = "discord"

    def send(self, plan: dict[str, Any], *, event=None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        del context
        if not _external_reply_allowed(plan):
            return {"sent": False, "reason": "external reply suppressed by response prompt policy"}
        channel_id = ""
        if event is not None:
            scope = getattr(event, "scope", None)
            channel_id = str(getattr(scope, "id", "") or "")
        messages = plan.get("messages") if isinstance(plan.get("messages"), list) else []
        results = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            results.append(self.send_channel_message(channel_id, str(message.get("text") or "")))
        return {"sent": any(item.get("sent") for item in results), "results": results}

    def send_channel_message(self, channel_id: str, text: str) -> dict[str, Any]:
        token = read_external_token("discord", kind="bot_token")
        if not token:
            return {"sent": False, "reason": "Discord bot token not configured"}
        if not channel_id or not text:
            return {"sent": False, "reason": "missing channel or text"}
        response = post_json(
            "https://discord.com/api/v10/channels/{}/messages".format(channel_id),
            {"Authorization": "Bot " + token},
            {"content": text[:2000], "allowed_mentions": {"parse": []}},
        )
        return {"sent": bool(response.get("ok")), "provider_response": response}


def _external_reply_allowed(plan: dict[str, Any]) -> bool:
    metadata = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
    action_plan = metadata.get("response_action_plan") if isinstance(metadata.get("response_action_plan"), dict) else {}
    if action_plan and not action_plan.get("external_reply", True):
        return False
    decision = metadata.get("response_prompt_decision") if isinstance(metadata.get("response_prompt_decision"), dict) else {}
    if str(decision.get("sensitivity") or "").lower() == "local_only":
        return False
    return True
