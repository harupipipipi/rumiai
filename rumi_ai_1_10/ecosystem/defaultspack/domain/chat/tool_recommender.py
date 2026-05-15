from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


TOOL_ASSIST_DEFAULT_MODE = "auto"
TOOL_ASSIST_MODES = {"auto", "all", "off"}
DEFAULT_TOOL_RECOMMENDATION_LIMIT = 8
DEFAULT_TOOL_RECOMMENDATION_THRESHOLD = 0.08

_WORD_RE = re.compile(r"[A-Za-z0-9_./:-]+|[\u3040-\u30ff\u3400-\u9fff]+")
_JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def effective_tool_assist_mode(settings: dict[str, Any] | None = None, *, pack_root: Path | None = None) -> str:
    """Return the selected tool-assist mode.

    The setting intentionally defaults to auto so a blank composer does not
    silently expose every tool to the model.
    """

    values = settings if isinstance(settings, dict) else _read_frontend_settings(pack_root)
    tools = values.get("tools") if isinstance(values, dict) else {}
    tools = tools if isinstance(tools, dict) else {}
    if tools.get("tool_assist_enabled") is False:
        return "off"
    mode = str(tools.get("tool_assist_mode") or TOOL_ASSIST_DEFAULT_MODE).strip().lower()
    return mode if mode in TOOL_ASSIST_MODES else TOOL_ASSIST_DEFAULT_MODE


def tool_assist_limit(settings: dict[str, Any] | None = None, *, pack_root: Path | None = None) -> int:
    values = settings if isinstance(settings, dict) else _read_frontend_settings(pack_root)
    tools = values.get("tools") if isinstance(values, dict) else {}
    tools = tools if isinstance(tools, dict) else {}
    try:
        limit = int(tools.get("tool_assist_limit", DEFAULT_TOOL_RECOMMENDATION_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_TOOL_RECOMMENDATION_LIMIT
    return max(1, min(24, limit))


def recommend_tool_ids(
    user_text: str,
    tools: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_TOOL_RECOMMENDATION_LIMIT,
    threshold: float = DEFAULT_TOOL_RECOMMENDATION_THRESHOLD,
) -> list[str]:
    query_vector = _text_vector(user_text)
    if not query_vector:
        return []
    scored: list[tuple[float, str]] = []
    for tool in tools:
        tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip()
        if not tool_id:
            continue
        score = _cosine_similarity(query_vector, _tool_vector(tool))
        score += _exact_boost(user_text, tool)
        if score >= threshold:
            scored.append((score, tool_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [tool_id for _, tool_id in scored[: max(1, limit)]]


def _read_frontend_settings(pack_root: Path | None = None) -> dict[str, Any]:
    root = pack_root or Path(__file__).resolve().parents[2]
    path = root / "user_data" / "shared" / "frontend_settings.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _tool_vector(tool: dict[str, Any]) -> Counter[str]:
    parts: list[str] = [
        str(tool.get("tool_id") or ""),
        str(tool.get("name") or ""),
        str(tool.get("summary") or ""),
        str(tool.get("category") or ""),
        " ".join(str(tag) for tag in tool.get("tags", []) if tag),
        " ".join(str(skill) for skill in tool.get("skills", []) if skill),
    ]
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    ui = tool.get("ui") if isinstance(tool.get("ui"), dict) else {}
    for container in (metadata, ui):
        parts.extend(
            str(container.get(key) or "")
            for key in (
                "description",
                "summary",
                "keywords",
                "group_id",
                "label",
                "source",
                "server_id",
                "server_name",
                "mcp_tool_name",
            )
        )
        for key in ("skills", "required_skills", "skill_ids"):
            value = container.get(key)
            if isinstance(value, list):
                parts.append(" ".join(str(item) for item in value if item))
            elif value:
                parts.append(str(value))
    schema = tool.get("schema") if isinstance(tool.get("schema"), dict) else {}
    parameters = schema.get("parameters") if isinstance(schema.get("parameters"), dict) else schema
    if isinstance(parameters, dict) and isinstance(parameters.get("inputSchema"), dict):
        parameters = parameters["inputSchema"]
    properties = parameters.get("properties") if isinstance(parameters, dict) else {}
    if isinstance(properties, dict):
        parts.append(" ".join(str(name) for name in properties.keys()))
        for value in properties.values():
            if isinstance(value, dict):
                parts.append(" ".join(str(value.get(key) or "") for key in ("title", "description")))
    return _text_vector(" ".join(parts))


def _text_vector(text: str) -> Counter[str]:
    normalized = str(text or "").casefold()
    vector: Counter[str] = Counter()
    for token in _WORD_RE.findall(normalized):
        token = token.strip(" \t\r\n.,!?()[]{}")
        if not token:
            continue
        vector[token] += 2
        if "_" in token:
            for part in token.split("_"):
                if part:
                    vector[part] += 1
        if _JAPANESE_RE.search(token):
            for gram in _char_ngrams(token):
                vector[gram] += 1
    return vector


def _char_ngrams(token: str, size: int = 2) -> list[str]:
    if len(token) <= size:
        return [token]
    return [token[index:index + size] for index in range(len(token) - size + 1)]


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = set(left) & set(right)
    numerator = sum(left[key] * right[key] for key in overlap)
    if numerator <= 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _exact_boost(user_text: str, tool: dict[str, Any]) -> float:
    haystack = str(user_text or "").casefold()
    if not haystack:
        return 0.0
    boost = 0.0
    tool_id = str(tool.get("tool_id") or "").casefold()
    if tool_id and tool_id in haystack:
        boost += 0.25
    for tag in tool.get("tags", []) or []:
        text = str(tag or "").casefold()
        if text and text in haystack:
            boost += 0.08
    return min(boost, 0.4)
