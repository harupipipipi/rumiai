from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from domain.webhook.endpoint import WebhookEndpoint


_LINE_ADDRESSING_CONTEXT_WINDOW_MS = 10 * 60 * 1000
_LINE_ADDRESSING_DEFAULT_ALIASES = (
    "rumi",
    "rumi_ai",
    "haru_clone_ai",
    "haru clone ai",
    "\u308b\u307f",
    "\u30eb\u30df",
)
_LINE_FOLLOWUP_RE = re.compile(
    r"^\s*(ok|okay|yes|yep|sure|please|go ahead|that one|option\s*[a-d]|"
    r"\u3046\u3093|\u306f\u3044|\u304a\u306d\u304c\u3044|\u304a\u9858\u3044|"
    r"\u305d\u308c|\u305d\u308c\u3067|\u3058\u3083\u3042|\u3058\u3083|"
    r"[a-d\uff21-\uff24]\s*(\u6848|\u3067)|"
    r"\u9032\u3081\u3066|\u3088\u308d\u3057\u304f)",
    re.IGNORECASE,
)


def decide_line_addressing(
    event: dict[str, Any],
    external_event,
    *,
    endpoint: WebhookEndpoint,
    mentioned: bool,
) -> dict[str, Any]:
    scope_type = getattr(getattr(external_event, "scope", None), "type", "")
    if scope_type == "user":
        return {
            "addressed": True,
            "reason": "direct LINE user chat",
            "confidence": 1.0,
            "signals": ["direct_user_chat"],
        }
    if scope_type not in {"group", "room"}:
        return {
            "addressed": False,
            "reason": "unsupported LINE source scope",
            "confidence": 0.0,
            "signals": ["unsupported_scope"],
        }
    if mentioned:
        return {
            "addressed": True,
            "reason": "LINE mention targets the bot",
            "confidence": 1.0,
            "signals": ["line_mention"],
        }

    text = _line_message_text(event)
    alias = _line_alias_match(text, _line_addressing_aliases(endpoint))
    if alias:
        return {
            "addressed": True,
            "reason": "message names a configured bot alias",
            "confidence": 0.92,
            "signals": ["alias"],
            "alias": alias,
        }

    history_signal = _line_history_addressing_signal(external_event, endpoint=endpoint, text=text)
    if bool(history_signal.get("matched")):
        return {
            "addressed": True,
            "reason": str(history_signal.get("reason") or "recent conversation context"),
            "confidence": float(history_signal.get("confidence") or 0.7),
            "signals": ["conversation_context"],
            "context": history_signal,
        }

    return {
        "addressed": False,
        "reason": "no mention, alias, or recent Rumi conversation context",
        "confidence": 0.2,
        "signals": [],
    }


def _line_message_text(event: dict[str, Any]) -> str:
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    if str(message.get("type") or "") != "text":
        return ""
    return str(message.get("text") or "").strip()


def _line_addressing_aliases(endpoint: WebhookEndpoint) -> list[str]:
    values: list[str] = []
    response = endpoint.response if isinstance(endpoint.response, dict) else {}
    conversation = endpoint.conversation if isinstance(endpoint.conversation, dict) else {}
    metadata = endpoint.metadata if isinstance(endpoint.metadata, dict) else {}
    for container in (metadata, response, conversation):
        for key in ("bot_aliases", "line_bot_aliases", "addressing_aliases", "assistant_names"):
            values.extend(_listish(container.get(key)))
    if not values:
        try:
            data = json.loads(_frontend_settings_path().read_text(encoding="utf-8"))
        except Exception:
            data = {}
        line_settings = data.get("line") if isinstance(data, dict) and isinstance(data.get("line"), dict) else {}
        values.extend(_listish(line_settings.get("bot_aliases")))
        values.extend(_listish(line_settings.get("addressing_aliases")))
    values.extend(_LINE_ADDRESSING_DEFAULT_ALIASES)
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            unique.append(text)
            seen.add(key)
    return unique


def _listish(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(",", "\n").splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    return [str(item or "").strip() for item in raw if str(item or "").strip()]


def _line_alias_match(text: str, aliases: list[str]) -> str:
    normalized = str(text or "").casefold()
    if not normalized:
        return ""
    for alias in aliases:
        candidate = str(alias or "").strip()
        if not candidate:
            continue
        folded = candidate.casefold()
        if _asciiish(folded):
            pattern = r"(?<![a-z0-9_])@?" + re.escape(folded) + r"(?![a-z0-9_])"
            if re.search(pattern, normalized):
                return candidate
            continue
        if candidate in text:
            return candidate
    return ""


def _asciiish(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _line_history_addressing_signal(external_event, *, endpoint: WebhookEndpoint, text: str) -> dict[str, Any]:
    if not str(text or "").strip():
        return {"matched": False, "reason": "empty text"}
    conversation_id = _line_external_conversation_id(external_event)
    if not conversation_id:
        return {"matched": False, "reason": "no prior external conversation"}
    try:
        from domain.chat.store import ChatStore

        conversation = ChatStore().get_conversation(conversation_id)
    except Exception as exc:
        return {"matched": False, "reason": "history lookup failed", "error": str(exc)}
    if not isinstance(conversation, dict):
        return {"matched": False, "reason": "prior external conversation missing"}
    messages = conversation.get("messages") if isinstance(conversation.get("messages"), list) else []
    if not messages:
        return {"matched": False, "reason": "conversation has no messages"}

    now_ms = int(getattr(external_event, "received_at", 0) or 0)
    window_ms = _line_addressing_context_window_ms(endpoint)
    for message in reversed(messages[-8:]):
        if not isinstance(message, dict):
            continue
        created_at = _message_created_at_ms(message)
        if now_ms and created_at and now_ms - created_at > window_ms:
            return {"matched": False, "reason": "recent Rumi context expired", "window_ms": window_ms}
        role = str(message.get("role") or "").strip()
        raw_text = _message_raw_text(message)
        if role == "assistant" and raw_text:
            if _assistant_invites_line_followup(raw_text) or _looks_like_line_followup(text):
                return {
                    "matched": True,
                    "reason": "message appears to continue the latest Rumi reply",
                    "confidence": 0.74,
                    "conversation_id": conversation_id,
                    "last_assistant_excerpt": raw_text[:240],
                    "window_ms": window_ms,
                }
            return {"matched": False, "reason": "latest Rumi reply did not invite a follow-up", "conversation_id": conversation_id}
    return {"matched": False, "reason": "no recent assistant message in prior context", "conversation_id": conversation_id}


def _line_external_conversation_id(external_event) -> str:
    try:
        from domain.integrations.store import IntegrationConversationStore

        return IntegrationConversationStore().get_conversation_id(
            str(getattr(external_event, "provider", "") or "line"),
            str(getattr(getattr(external_event, "conversation", None), "id", "") or ""),
        )
    except Exception:
        return ""


def _line_addressing_context_window_ms(endpoint: WebhookEndpoint) -> int:
    response = endpoint.response if isinstance(endpoint.response, dict) else {}
    conversation = endpoint.conversation if isinstance(endpoint.conversation, dict) else {}
    metadata = endpoint.metadata if isinstance(endpoint.metadata, dict) else {}
    raw: Any = None
    for container in (metadata, response, conversation):
        for key in ("line_addressing_context_window_ms", "group_addressing_context_window_ms"):
            if key in container:
                raw = container.get(key)
                break
        if raw is not None:
            break
    if raw is None:
        for container in (metadata, response, conversation):
            for key in ("line_addressing_context_window_seconds", "group_addressing_context_window_seconds"):
                if key in container:
                    try:
                        raw = int(container.get(key)) * 1000
                    except Exception:
                        raw = None
                    break
            if raw is not None:
                break
    try:
        value = int(raw)
    except Exception:
        value = _LINE_ADDRESSING_CONTEXT_WINDOW_MS
    return max(60_000, min(value, 60 * 60 * 1000))


def _message_created_at_ms(message: dict[str, Any]) -> int:
    try:
        return int(message.get("created_at") or 0)
    except Exception:
        return 0


def _message_raw_text(message: dict[str, Any]) -> str:
    text = str(message.get("raw_text") or "").strip()
    if text:
        return text
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return " ".join(part.strip() for part in parts if part.strip())
    return ""


def _assistant_invites_line_followup(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if "?" in value or "\uff1f" in value:
        return True
    markers = (
        "\u3069\u3046\u3057\u307e\u3059\u304b",
        "\u3069\u3046\u3059\u308b",
        "\u6559\u3048\u3066",
        "\u9078\u3093\u3067",
        "\u78ba\u8a8d",
        "\u304a\u9858\u3044",
        "\u5fc5\u8981\u3067\u3059\u304b",
    )
    return any(marker in value for marker in markers)


def _looks_like_line_followup(text: str) -> bool:
    return bool(_LINE_FOLLOWUP_RE.search(str(text or "").strip()))


def _frontend_settings_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH", "").strip()
    return Path(override) if override else Path(__file__).resolve().parents[3] / "user_data" / "shared" / "frontend_settings.json"
