from __future__ import annotations

import ast
import json
import re
from typing import Any


DEFAULT_MAX_TOOL_CALLS = 64


_TEXT_TOOL_USE_RE = re.compile(
    r"(\{[^{}]*(?:['\"]type['\"]\s*:\s*['\"]tool_use['\"]|['\"]name['\"]\s*:\s*['\"][A-Za-z0-9_.-]+['\"])[\s\S]*?\})"
)
_SECRET_KEYS = {"approval_token", "token", "api_key", "authorization", "credential", "secret", "password"}


def tool_support_settings(params: dict[str, Any] | None) -> dict[str, Any]:
    params = params if isinstance(params, dict) else {}
    raw = params.get("tool_support")
    settings = dict(raw) if isinstance(raw, dict) else {}
    settings.setdefault("enabled", True)
    settings.setdefault("loop_detection", True)
    settings.setdefault("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)
    settings.setdefault("repeated_action_limit", 4)
    settings.setdefault("self_evaluation", False)
    settings.setdefault("app_scoped_desktop_actions", True)
    return settings


def effective_max_tool_calls(
    explicit_limit: int | None,
    params: dict[str, Any] | None,
    support: dict[str, Any] | None = None,
) -> int:
    support = support if isinstance(support, dict) else tool_support_settings(params)
    raw = explicit_limit
    if raw is None and isinstance(params, dict):
        raw = params.get("max_tool_calls")
    if raw is None:
        raw = support.get("max_tool_calls")
    try:
        value = int(raw)
    except Exception:
        value = DEFAULT_MAX_TOOL_CALLS
    if value <= 0:
        value = DEFAULT_MAX_TOOL_CALLS
    return max(1, min(value, 256))


def extract_text_tool_uses(response: dict[str, Any], *, allowed_names: set[str] | None = None) -> list[dict[str, Any]]:
    blocks = response.get("content", []) if isinstance(response, dict) else []
    if not isinstance(blocks, list):
        return []
    extracted: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        for candidate in _candidate_dicts(text):
            normalized = _normalize_tool_use(candidate, allowed_names=allowed_names)
            if normalized is not None:
                extracted.append(normalized)
    return extracted


def strip_text_tool_use_blocks(response: dict[str, Any]) -> dict[str, Any]:
    next_response = dict(response or {})
    content = []
    for block in next_response.get("content", []) or []:
        if not isinstance(block, dict) or block.get("type") != "text":
            content.append(block)
            continue
        text = str(block.get("text") or "")
        if "tool_use" in text and ("'name'" in text or '"name"' in text):
            continue
        content.append(block)
    next_response["content"] = content
    return next_response


def loop_signature(tool_name: str, arguments: dict[str, Any]) -> str:
    return "{}:{}".format(tool_name, json.dumps(_stable(arguments), ensure_ascii=False, sort_keys=True))


def semantic_loop_signature(tool_name: str, arguments: dict[str, Any]) -> str:
    stable = _stable(arguments)
    if not isinstance(stable, dict):
        return loop_signature(tool_name, arguments)
    action = str(stable.get("action") or "").strip().lower()
    normalized: dict[str, Any] = {
        "tool": tool_name,
        "action": action,
        "target": stable.get("target") or stable.get("target_scope"),
        "app": stable.get("app") or stable.get("name"),
        "query": stable.get("query"),
    }
    if action in {"click", "computer.click", "move", "computer.move", "zoom", "computer.zoom"}:
        point = stable.get("point")
        x = stable.get("x")
        y = stable.get("y")
        if isinstance(point, list) and len(point) >= 2:
            y, x = point[0], point[1]
        normalized["x_bucket"] = _bucket_number(x, 80)
        normalized["y_bucket"] = _bucket_number(y, 80)
        normalized["coordinate_space"] = stable.get("coordinate_space")
    elif action in {"type", "computer.type"}:
        normalized["text"] = stable.get("text") or stable.get("input_text")
    elif action in {"key", "computer.key", "hotkey", "computer.hotkey"}:
        normalized["key"] = stable.get("key") or stable.get("keys") or stable.get("combo")
    return "{}:{}".format(tool_name, json.dumps(normalized, ensure_ascii=False, sort_keys=True))


class ToolLoopGuard:
    def __init__(self, *, enabled: bool = True, repeated_action_limit: int = 4) -> None:
        self.enabled = enabled
        self.repeated_action_limit = max(2, int(repeated_action_limit or 4))
        self._counts: dict[str, int] = {}
        self._semantic_counts: dict[str, int] = {}

    def record(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        signature = loop_signature(tool_name, arguments)
        count = self._counts.get(signature, 0) + 1
        self._counts[signature] = count
        if count < self.repeated_action_limit:
            semantic_signature = semantic_loop_signature(tool_name, arguments)
            semantic_count = self._semantic_counts.get(semantic_signature, 0) + 1
            self._semantic_counts[semantic_signature] = semantic_count
            if semantic_count < self.repeated_action_limit:
                return None
            return {
                "reason": "repeated_semantic_tool_call",
                "tool_name": tool_name,
                "repeat_count": semantic_count,
                "repeated_action_limit": self.repeated_action_limit,
                "signature": semantic_signature,
            }
        return {
            "reason": "repeated_tool_call",
            "tool_name": tool_name,
            "repeat_count": count,
            "repeated_action_limit": self.repeated_action_limit,
            "signature": signature,
        }


def result_needs_support(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("status") == "error":
        return True
    data = result.get("data")
    if isinstance(data, dict):
        if data.get("status") == "error":
            return True
        widget = data.get("widget")
        if isinstance(widget, dict):
            return bool(widget.get("requires_approval") or widget.get("approval_required") or widget.get("status") == "error")
    return False


def support_message_for_tool_result(tool_name: str, result: Any) -> dict[str, Any] | None:
    if not result_needs_support(result):
        return None
    return {
        "role": "system",
        "content": (
            "Tool support: inspect the previous tool result before continuing. "
            "If it requires approval, stop and ask for approval or retry only after an approval token is available. "
            "If it failed, change strategy instead of repeating the same call. "
            "For desktop/browser work, prefer app-scoped screenshots/actions: computer.app.find, computer.app.focus, "
            "then screenshot/click/type with target='app' and app set to the intended app."
        ),
    }


def _candidate_dicts(text: str) -> list[Any]:
    values: list[Any] = []
    for raw in [text, *_TEXT_TOOL_USE_RE.findall(text)]:
        raw = raw.strip()
        if not raw:
            continue
        for parser in (json.loads, ast.literal_eval):
            try:
                values.append(parser(raw))
                break
            except Exception:
                continue
    return values


def _normalize_tool_use(value: Any, *, allowed_names: set[str] | None = None) -> dict[str, Any] | None:
    if isinstance(value, list):
        return None
    if not isinstance(value, dict):
        return None
    if str(value.get("type") or "").strip() not in {"tool_use", "tool_call"} and "name" not in value:
        return None
    name = str(value.get("name") or value.get("tool_name") or "").strip()
    if not name:
        return None
    if allowed_names is not None and name not in allowed_names:
        return None
    tool_input = value.get("input", value.get("arguments", {}))
    if isinstance(tool_input, str):
        tool_input = _parse_input_string(tool_input)
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}
    return {
        "type": "tool_use",
        "id": str(value.get("id") or value.get("tool_call_id") or ""),
        "name": name,
        "input": tool_input,
        "source": "text_tool_use",
    }


def _parse_input_string(value: str) -> Any:
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(value)
        except Exception:
            continue
    return {"value": value}


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable(item)
            for key, item in value.items()
            if str(key).lower() not in _SECRET_KEYS and not str(key).startswith("_")
        }
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


def _bucket_number(value: Any, bucket: int) -> Any:
    try:
        numeric = float(value)
    except Exception:
        return None
    return int(round(numeric / bucket) * bucket)
