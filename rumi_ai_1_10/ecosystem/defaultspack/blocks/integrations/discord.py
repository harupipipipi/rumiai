from __future__ import annotations

from typing import Any, Dict

from blocks._common import ok, error
from blocks.integrations.common import allow_unsigned_webhook_dev, headers_from_request, raw_body_bytes, text_limit
from domain.integrations.chat_bridge import dispatch_external_message
from domain.integrations.http_client import post_json
from domain.integrations.secrets import get_integration_secret, load_integration_secrets_into_env


DISCORD_PING = 1
DISCORD_APPLICATION_COMMAND = 2
DISCORD_MESSAGE_WITH_SOURCE = 4


def run(input_data, context):
    load_integration_secrets_into_env()
    headers = headers_from_request(input_data)
    raw_body = raw_body_bytes(input_data)
    verification = _verify_discord(headers, raw_body)
    if not verification["ok"]:
        return {**error(verification["reason"], "SIGNATURE_INVALID"), "_http_status": 401}

    payload_type = input_data.get("type")
    if payload_type == DISCORD_PING:
        return {"type": DISCORD_PING}

    if payload_type == DISCORD_APPLICATION_COMMAND:
        result = _handle_interaction(input_data, context)
        return {
            "type": DISCORD_MESSAGE_WITH_SOURCE,
            "data": {
                "content": text_limit(result.get("assistant_text") or "応答を生成できませんでした。", 2000),
                "allowed_mentions": {"parse": []},
            },
            "rumi": {key: value for key, value in result.items() if key != "assistant_text"},
            "verified": verification["verified"],
        }

    if str(input_data.get("t") or "").upper() == "MESSAGE_CREATE" or input_data.get("content"):
        result = _handle_message_create(input_data, context)
        return ok({**result, "verified": verification["verified"]})

    return ok({"ignored": True, "reason": "unsupported discord payload", "verified": verification["verified"]})


def _handle_interaction(input_data: Dict[str, Any], context) -> Dict[str, Any]:
    data = input_data.get("data") if isinstance(input_data.get("data"), dict) else {}
    text = _interaction_text(data)
    channel_id = str(input_data.get("channel_id") or "")
    user_id = _interaction_user_id(input_data)
    external_key = "|".join(["discord", str(input_data.get("guild_id") or "dm"), channel_id or user_id or "interaction"])
    return dispatch_external_message(
        provider="discord",
        text=text,
        external_key=external_key,
        title="Discord " + (channel_id or user_id or "interaction"),
        event_id=str(input_data.get("id") or ""),
        metadata={
            "interaction_id": input_data.get("id"),
            "application_id": input_data.get("application_id"),
            "guild_id": input_data.get("guild_id"),
            "channel_id": channel_id,
            "user_id": user_id,
            "interaction_name": data.get("name"),
        },
        context=context,
    )


def _handle_message_create(input_data: Dict[str, Any], context) -> Dict[str, Any]:
    data = input_data.get("d") if isinstance(input_data.get("d"), dict) else input_data
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    if author.get("bot"):
        return {"status": "ignored", "reason": "bot message", "assistant_text": ""}
    channel_id = str(data.get("channel_id") or input_data.get("channel_id") or "")
    user_id = str(author.get("id") or data.get("user_id") or "")
    content = str(data.get("content") or input_data.get("content") or "")
    external_key = "|".join(["discord", str(data.get("guild_id") or "dm"), channel_id or user_id or "message"])
    result = dispatch_external_message(
        provider="discord",
        text=content,
        external_key=external_key,
        title="Discord " + (channel_id or user_id or "message"),
        event_id=str(data.get("id") or input_data.get("id") or ""),
        metadata={
            "guild_id": data.get("guild_id"),
            "channel_id": channel_id,
            "user_id": user_id,
            "message_id": data.get("id"),
        },
        context=context,
    )
    reply = _send_discord_channel_message(channel_id, result.get("assistant_text", ""))
    return {**result, "reply": reply}


def _interaction_text(data: Dict[str, Any]) -> str:
    options = data.get("options") if isinstance(data.get("options"), list) else []
    for option in options:
        if not isinstance(option, dict):
            continue
        value = option.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    name = str(data.get("name") or "").strip()
    return name or "hello"


def _interaction_user_id(input_data: Dict[str, Any]) -> str:
    member = input_data.get("member") if isinstance(input_data.get("member"), dict) else {}
    user = member.get("user") if isinstance(member.get("user"), dict) else input_data.get("user")
    if isinstance(user, dict):
        return str(user.get("id") or "")
    return ""


def _verify_discord(headers: Dict[str, str], raw_body: bytes) -> Dict[str, Any]:
    public_key = get_integration_secret("discord", "DISCORD_PUBLIC_KEY")
    if not public_key:
        if allow_unsigned_webhook_dev():
            return {"ok": True, "verified": False, "reason": "unsigned dev mode enabled"}
        return {"ok": False, "verified": False, "reason": "Discord public key not configured"}
    signature = headers.get("x-signature-ed25519", "")
    timestamp = headers.get("x-signature-timestamp", "")
    if not signature or not timestamp:
        return {"ok": False, "verified": False, "reason": "missing Discord signature headers"}
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
        key.verify(bytes.fromhex(signature), timestamp.encode("utf-8") + raw_body)
    except Exception:
        return {"ok": False, "verified": False, "reason": "Discord signature mismatch"}
    return {"ok": True, "verified": True, "reason": ""}


def _send_discord_channel_message(channel_id: str, text: str) -> Dict[str, Any]:
    token = get_integration_secret("discord", "DISCORD_BOT_TOKEN")
    if not token:
        return {"sent": False, "reason": "DISCORD_BOT_TOKEN not configured"}
    if not channel_id or not text:
        return {"sent": False, "reason": "missing channel or text"}
    response = post_json(
        "https://discord.com/api/v10/channels/{}/messages".format(channel_id),
        {"Authorization": "Bot " + token},
        {"content": text_limit(text, 2000), "allowed_mentions": {"parse": []}},
    )
    return {"sent": bool(response.get("ok")), "provider_response": response}
