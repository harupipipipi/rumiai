from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_TEXT_CALL_RE = re.compile(
    r"^call:(?P<head>[A-Za-z_][A-Za-z0-9_.:-]{0,200})\s*(?P<args>\{.*\})\s*$",
    re.DOTALL,
)

_COMPUTER_TOOL_PREFERENCE = ("computer_use", "browser_computer", "browser_use")
_COMPUTER_NAMESPACE_ALIASES = {
    "atlas",
    "browser",
    "chatgpt_atlas",
    "chatgptatlas",
    "chrome",
    "computer",
    "desktop",
    "edge",
    "firefox",
    "google_chrome",
    "googlechrome",
    "msedge",
    "safari",
    "vivaldi",
}


def text_tool_calls_from_response(
    response: dict[str, Any] | None,
    connected_tool_names: set[str] | list[str] | tuple[str, ...] | None,
) -> list[dict[str, Any]]:
    """Recover provider-emitted text calls such as ``call:browser.open_url{...}``.

    Some OpenAI-compatible providers accept tools but weaker/non-native tool
    callers occasionally emit the prompt's compact call notation as visible
    text. To avoid accidental side effects, only parse responses whose entire
    visible text is a single ``call:...{...}`` expression and only map it to a
    tool that is already connected for this turn.
    """

    connected = {str(name or "").strip() for name in connected_tool_names or [] if str(name or "").strip()}
    if not connected or not isinstance(response, dict):
        return []
    text = _response_text(response).strip()
    if not text:
        return []
    match = _TEXT_CALL_RE.fullmatch(text)
    if match is None:
        return []
    parsed = _parse_call_head(str(match.group("head") or ""), connected)
    if parsed is None:
        return []
    tool_name, action = parsed
    arguments = _parse_arguments_object(str(match.group("args") or ""))
    if action and not str(arguments.get("action") or "").strip():
        arguments["action"] = action
    call_id = "text_call_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return [{"type": "tool_use", "id": call_id, "name": tool_name, "input": arguments}]


def _response_text(response: dict[str, Any]) -> str:
    blocks = response.get("content", [])
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts)


def _parse_call_head(head: str, connected: set[str]) -> tuple[str, str] | None:
    for tool_name, action in _head_candidates(head):
        if tool_name in connected:
            return tool_name, action

    namespace, action = _namespace_action(head)
    if namespace not in _COMPUTER_NAMESPACE_ALIASES:
        return None
    target = next((name for name in _COMPUTER_TOOL_PREFERENCE if name in connected), "")
    if not target:
        return None
    return target, action


def _head_candidates(head: str) -> list[tuple[str, str]]:
    text = str(head or "").strip()
    if not text:
        return []
    candidates = [(text, "")]
    for separator in (":", "."):
        if separator not in text:
            continue
        base, suffix = text.split(separator, 1)
        if base and suffix:
            candidates.append((base.strip(), suffix.strip()))
    return candidates


def _namespace_action(head: str) -> tuple[str, str]:
    text = str(head or "").strip()
    if ":" in text:
        namespace, action = text.split(":", 1)
        return namespace.strip(), action.strip()
    if "." in text:
        namespace, action = text.split(".", 1)
        return namespace.strip(), action.strip()
    return text, ""


def _parse_arguments_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    if not (text.startswith("{") and text.endswith("}")):
        return {}
    inner = text[1:-1].strip()
    if not inner:
        return {}
    arguments: dict[str, Any] = {}
    for part in _split_relaxed_fields(inner):
        key, separator, value = _split_relaxed_field(part)
        if not separator:
            continue
        clean_key = _strip_quotes(key.strip())
        if clean_key:
            arguments[clean_key] = _parse_relaxed_value(value.strip())
    return arguments


def _split_relaxed_fields(inner: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote = ""
    depth = 0
    escaped = False
    for index, char in enumerate(inner):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char in "{[":
            depth += 1
            continue
        if char in "}]":
            depth = max(0, depth - 1)
            continue
        if char == "," and depth == 0:
            parts.append(inner[start:index].strip())
            start = index + 1
    tail = inner[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _split_relaxed_field(part: str) -> tuple[str, str, str]:
    quote = ""
    escaped = False
    for index, char in enumerate(part):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char in {":", "="}:
            return part[:index], char, part[index + 1 :]
    return part, "", ""


def _parse_relaxed_value(value: str) -> Any:
    text = value.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return float(text) if "." in text else int(text)
    return _strip_quotes(text)


def _strip_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text
