from __future__ import annotations

import time
from copy import deepcopy
from typing import Any


DIRECTIVE_METADATA_KEY = "directive_layer"
DIRECTIVE_SCOPE = "conversation"
DIRECTIVE_ROLE = "developer"
DIRECTIVE_LABEL = "Directive Layer"
DIRECTIVE_MAX_CHARS = 40_000
CLEAR_DIRECTIVE_TOKENS = {"clear", "--clear"}


def is_clear_directive_instruction(value: Any) -> bool:
    return str(value or "").strip().lower() in CLEAR_DIRECTIVE_TOKENS


def normalize_directive(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    content = str(value.get("content") or value.get("instruction") or "").strip()
    if not content:
        return None
    scope = str(value.get("scope") or DIRECTIVE_SCOPE).strip().lower() or DIRECTIVE_SCOPE
    if scope != DIRECTIVE_SCOPE:
        return None
    return {
        "active": True,
        "scope": DIRECTIVE_SCOPE,
        "role": DIRECTIVE_ROLE,
        "label": str(value.get("label") or DIRECTIVE_LABEL).strip() or DIRECTIVE_LABEL,
        "content": content[:DIRECTIVE_MAX_CHARS],
        "source": str(value.get("source") or "slash_command").strip() or "slash_command",
        "source_command": str(value.get("source_command") or "directive").strip()
        or "directive",
        "updated_at": int(value.get("updated_at") or _now_ms()),
        "note": (
            "Rumi conversation directive; materialized above normal user content as "
            "developer/instructions-equivalent input when supported, with system-role fallback."
        ),
    }


def conversation_directive(conversation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(conversation, dict):
        return None
    metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
    return normalize_directive(metadata.get(DIRECTIVE_METADATA_KEY))


def set_directive_metadata(
    metadata: dict[str, Any] | None,
    instruction: Any,
    *,
    source_command: str = "directive",
) -> tuple[dict[str, Any], dict[str, Any]]:
    content = str(instruction or "").strip()
    if not content:
        raise ValueError("directive instruction is required")
    updated = deepcopy(metadata) if isinstance(metadata, dict) else {}
    directive = normalize_directive(
        {
            "content": content,
            "source": "slash_command",
            "source_command": source_command,
            "updated_at": _now_ms(),
        }
    )
    if directive is None:
        raise ValueError("directive instruction is required")
    updated[DIRECTIVE_METADATA_KEY] = directive
    return updated, directive


def clear_directive_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    updated = deepcopy(metadata) if isinstance(metadata, dict) else {}
    updated.pop(DIRECTIVE_METADATA_KEY, None)
    return updated


def directive_context_message(directive: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_directive(directive)
    if normalized is None:
        raise ValueError("directive is not active")
    return {
        "role": DIRECTIVE_ROLE,
        "content": (
            "[Rumi conversation directive - user-configurable, conversation scope]\n"
            "Apply this directive after Rumi/controller instructions and before normal user "
            "content. It does not grant tool, file, network, approval, or security bypass "
            "privileges.\n\n"
            + normalized["content"]
        ),
    }


def insert_conversation_directive_message(
    messages: list[dict[str, Any]],
    conversation: dict[str, Any] | None,
) -> dict[str, Any] | None:
    directive = conversation_directive(conversation)
    if directive is None:
        return None
    insert_at = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or str(message.get("role") or "") != "system":
            insert_at = index
            break
        insert_at = index + 1
    messages.insert(insert_at, directive_context_message(directive))
    return directive


def _now_ms() -> int:
    return int(time.time() * 1000)
