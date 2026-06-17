from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from domain.external.response_adapter import ResponseAdapter
from domain.external.targeting import ExternalOrigin, origin_from_external_event
from domain.external.token_store import read_external_token
from domain.integrations.http_client import post_json


class LineResponseAdapter(ResponseAdapter):
    provider = "line"

    def send(self, plan: dict[str, Any], *, event=None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        if not _external_reply_allowed(plan):
            return {"sent": False, "reason": "external reply suppressed by response prompt policy"}
        messages = _line_messages(plan)
        if not messages:
            return {"sent": False, "reason": "missing LINE messages"}
        mode = _send_mode(plan, context)
        origin = origin_from_external_event(event) if event is not None else _origin_from_context(context)
        if mode == "reply_to_origin":
            if not origin.can_reply or not origin.reply_token:
                return _reply_unavailable_result("missing reply token", mode, origin, context, messages)
            if _reply_expired(origin):
                return _reply_unavailable_result("LINE reply token expired; push/post is recommended", mode, origin, context, messages)
            result = self.send_reply_messages(origin.reply_token, messages)
            if _reply_token_invalid(result):
                return _reply_unavailable_result("LINE reply token expired or already used; push/post is recommended", mode, origin, context, messages, reply_result=result)
            return result
        if mode == "push_to_origin":
            if not _push_allowed(context, origin):
                return {"sent": False, "reason": "push not allowed", "mode": mode, "origin": origin.as_dict()}
            if not origin.source_id:
                return {"sent": False, "reason": "missing push target", "mode": mode, "origin": origin.as_dict()}
            return self.send_push_messages(origin.source_id, messages)
        if mode == "push_to_explicit_target":
            target_id = _explicit_target(plan, context)
            if not target_id:
                return {"sent": False, "reason": "missing explicit push target", "mode": mode}
            return self.send_push_messages(target_id, messages)
        return {"sent": False, "reason": f"unsupported LINE send mode: {mode}", "mode": mode}

    def send_text_reply(self, reply_token: str, text: str) -> dict[str, Any]:
        messages = _text_to_messages(text)
        return self.send_reply_messages(reply_token, messages)

    def send_reply_messages(self, reply_token: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        token = read_external_token("line", kind="channel_access_token")
        if not token:
            return {"sent": False, "reason": "LINE channel access token not configured"}
        if not reply_token or not messages:
            return {"sent": False, "reason": "missing reply token or messages"}
        response = post_json(
            "https://api.line.me/v2/bot/message/reply",
            {"Authorization": "Bearer " + token},
            {"replyToken": reply_token, "messages": messages[:5]},
        )
        return {"sent": bool(response.get("ok")), "provider_response": response}

    def send_text_push(self, target_id: str, text: str) -> dict[str, Any]:
        messages = _text_to_messages(text)
        return self.send_push_messages(target_id, messages)

    def send_push_messages(self, target_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        token = read_external_token("line", kind="channel_access_token")
        if not token:
            return {"sent": False, "reason": "LINE channel access token not configured"}
        if not target_id or not messages:
            return {"sent": False, "reason": "missing push target or messages"}
        response = post_json(
            "https://api.line.me/v2/bot/message/push",
            {"Authorization": "Bearer " + token},
            {"to": target_id, "messages": messages[:5]},
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


def _line_messages(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw_messages = plan.get("messages") if isinstance(plan.get("messages"), list) else []
    messages: list[dict[str, Any]] = []
    for message in raw_messages:
        if not isinstance(message, dict):
            continue
        message_type = str(message.get("type") or "text")
        if message_type == "text":
            text = str(message.get("text") or "").strip()
            if text:
                messages.append({"type": "text", "text": text[:5000]})
        elif message_type == "image":
            image = _line_image_message(message)
            if image:
                messages.append(image)
        if len(messages) >= 5:
            return messages
    raw_files = plan.get("files") if isinstance(plan.get("files"), list) else []
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        image = _line_image_message(item)
        if image:
            messages.append(image)
        if len(messages) >= 5:
            break
    return messages


def _line_image_message(item: dict[str, Any]) -> dict[str, str] | None:
    mime = str(item.get("mime_type") or item.get("mime") or "").strip().lower()
    if mime and mime not in {"image/jpeg", "image/png"}:
        return None
    image_url = item.get("image_url") if isinstance(item.get("image_url"), dict) else {}
    original = str(
        item.get("originalContentUrl")
        or item.get("original_content_url")
        or item.get("url")
        or item.get("href")
        or image_url.get("url")
        or ""
    ).strip()
    preview = str(item.get("previewImageUrl") or item.get("preview_image_url") or item.get("preview_url") or original).strip()
    if not (_public_https_url(original) and _public_https_url(preview)):
        return None
    return {
        "type": "image",
        "originalContentUrl": original[:1000],
        "previewImageUrl": preview[:1000],
    }


def _public_https_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def _text_to_messages(text: str) -> list[dict[str, Any]]:
    cleaned = str(text or "").strip()
    return [{"type": "text", "text": cleaned[:5000]}] if cleaned else []


def _reply_expired(origin: ExternalOrigin) -> bool:
    if not origin.reply_expires_at_ms:
        return False
    return int(time.time() * 1000) >= int(origin.reply_expires_at_ms)


def _reply_token_invalid(result: dict[str, Any]) -> bool:
    if bool(result.get("sent")):
        return False
    response = result.get("provider_response") if isinstance(result.get("provider_response"), dict) else {}
    status = int(response.get("status") or 0)
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    message = str(body.get("message") or body.get("error") or body).lower()
    return status == 400 and "reply token" in message and ("invalid" in message or "expired" in message or "used" in message)


def _reply_unavailable_result(
    reason: str,
    mode: str,
    origin: ExternalOrigin,
    context: dict[str, Any] | None,
    messages: list[dict[str, Any]],
    *,
    reply_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "sent": False,
        "reason": reason,
        "mode": mode,
        "origin": origin.as_dict(),
        "error_code": "LINE_REPLY_TOKEN_UNAVAILABLE",
        "post_recommended": True,
        "recommendation": "reply期限切れ/使用済みです。LINE push/postを使ってください。",
    }
    if reply_result is not None:
        result["reply"] = reply_result
    if _auto_post_on_reply_failure(context):
        if not _push_allowed({**(context or {}), "allow_push": True}, origin):
            result["post"] = {"sent": False, "reason": "push target unavailable", "mode": "push_to_origin"}
            return result
        result["post"] = LineResponseAdapter().send_push_messages(origin.source_id, messages)
        result["sent"] = bool(result["post"].get("sent"))
        result["mode"] = "reply_failed_auto_post"
    return result


def _auto_post_on_reply_failure(context: dict[str, Any] | None) -> bool:
    context = context if isinstance(context, dict) else {}
    if bool(context.get("line_auto_post_on_reply_failure") or context.get("auto_post_on_reply_failure")):
        return True
    settings = context.get("hook_settings") if isinstance(context.get("hook_settings"), dict) else {}
    return bool(settings.get("line_auto_post_on_reply_failure") or settings.get("auto_post_on_reply_failure"))


def _send_mode(plan: dict[str, Any], context: dict[str, Any] | None) -> str:
    context = context if isinstance(context, dict) else {}
    metadata = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
    output = metadata.get("output") if isinstance(metadata.get("output"), dict) else {}
    mode = str(
        context.get("send_mode")
        or context.get("line_send_mode")
        or metadata.get("send_mode")
        or metadata.get("line_send_mode")
        or output.get("send_mode")
        or plan.get("mode")
        or "reply_to_origin"
    ).strip()
    aliases = {
        "": "reply_to_origin",
        "same_response": "reply_to_origin",
        "same_source_reply": "reply_to_origin",
        "line_reply_or_push": "reply_to_origin",
        "reply_or_push": "reply_to_origin",
        "push_to_saved_origin": "push_to_origin",
        "send_to_explicit_target": "push_to_explicit_target",
    }
    return aliases.get(mode, mode)


def _origin_from_context(context: dict[str, Any] | None) -> ExternalOrigin:
    context = context if isinstance(context, dict) else {}
    raw = context.get("origin") if isinstance(context.get("origin"), dict) else {}
    source_type = str(raw.get("source_type") or context.get("source_type") or "unknown")
    source_id = str(raw.get("source_id") or context.get("source_id") or "")
    reply_token = str(raw.get("reply_token") or context.get("reply_token") or "")
    mode = str(raw.get("mode") or context.get("mode") or "active")
    return ExternalOrigin(
        provider="line",
        workspace_id=str(raw.get("workspace_id") or context.get("workspace_id") or "unknown"),
        source_type=source_type,
        source_id=source_id,
        actor_id=str(raw.get("actor_id") or context.get("actor_id") or "unknown"),
        conversation_id=str(raw.get("conversation_id") or context.get("conversation_id") or ""),
        reply_token=reply_token,
        reply_expires_at_ms=raw.get("reply_expires_at_ms") if isinstance(raw.get("reply_expires_at_ms"), int) else None,
        mode=mode,
        can_reply=bool(reply_token) and mode != "standby",
        can_push=bool(source_id) and mode != "standby",
    )


def _push_allowed(context: dict[str, Any] | None, origin: ExternalOrigin) -> bool:
    if not origin.can_push:
        return False
    context = context if isinstance(context, dict) else {}
    if bool(context.get("allow_push")):
        return True
    record = context.get("source_record") if isinstance(context.get("source_record"), dict) else {}
    source = record.get("source") if isinstance(record.get("source"), dict) else record
    return bool(source.get("allow_push"))


def _explicit_target(plan: dict[str, Any], context: dict[str, Any] | None) -> str:
    context = context if isinstance(context, dict) else {}
    metadata = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
    output = metadata.get("output") if isinstance(metadata.get("output"), dict) else {}
    return str(
        context.get("target_id")
        or context.get("line_target_id")
        or output.get("target_id")
        or output.get("user_id")
        or output.get("group_id")
        or output.get("room_id")
        or ""
    ).strip()
