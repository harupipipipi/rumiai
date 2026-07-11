from __future__ import annotations

import re
from typing import Any

from ..mention import extract_mention_values, iter_mention_tokens

ANGLE_AGENT_RE = re.compile(r"<@!?([A-Za-z0-9_][A-Za-z0-9_-]*)>")
CHANNEL_RE = re.compile(r"(?<![\w.])#([A-Za-z0-9_][A-Za-z0-9_-]*)")
COMMAND_RE = re.compile(r"(^|\s)/([A-Za-z0-9_][A-Za-z0-9_-]*)")


def parse_mentions(
    text: str,
    known_agent_ids: list[str] | None = None,
) -> dict[str, Any]:
    content = str(text or "")
    agents = _dedupe(
        [
            *(match.group(1).lower() for match in ANGLE_AGENT_RE.finditer(content)),
            *(
                value.lower()
                for value in extract_mention_values(content, known_agent_ids)
            ),
        ]
    )
    channels = _dedupe(match.group(1).lower() for match in CHANNEL_RE.finditer(content))
    commands = _dedupe(match.group(2).lower() for match in COMMAND_RE.finditer(content))
    return {
        "agent_mentions": agents,
        "channel_mentions": channels,
        "commands": commands,
        "rich_requested": "rich" in commands,
    }


def sanitize_agent_mentions_for_gate(text: str) -> str:
    content = ANGLE_AGENT_RE.sub(lambda match: "at " + match.group(1), str(text or ""))
    for mention in reversed(iter_mention_tokens(content)):
        content = (
            content[: mention.start]
            + f"at {mention.value}"
            + content[mention.end :]
        )
    return content


def _dedupe(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip().lstrip("@#").lower()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
