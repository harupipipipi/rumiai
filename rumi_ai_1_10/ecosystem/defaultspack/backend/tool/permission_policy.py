"""JSON-backed tool permission policy helpers."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from domain.tool.autonomy import autonomous_tool_execution_allowed
from domain.tool.security import is_safe_first_party_memo_tool


_ACTION_ALLOW = "allow"
_ACTION_DENY = "deny"
_ACTION_ASK = "ask"
_VALID_ACTIONS = {_ACTION_ALLOW, _ACTION_DENY, _ACTION_ASK}

_DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "default_action": _ACTION_ASK,
    "tools": {},
    "tags": {},
    "execution_types": {},
    "mcp_servers": {},
    "updated_at": "",
}


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_policy_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_TOOL_PERMISSION_POLICY_PATH", "").strip()
    if override:
        return Path(override)
    return _pack_root() / "user_data" / "shared" / "tools" / "permission_policy.json"


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _normalize_action(value: Any, default: str = _ACTION_ASK) -> str:
    action = str(value or default).strip().lower()
    if action not in _VALID_ACTIONS:
        return default
    return action


def _normalize_rule_map(value: Any) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not isinstance(value, dict):
        return result
    for key, rule in value.items():
        if isinstance(rule, dict):
            action = _normalize_action(rule.get("action"))
        else:
            action = _normalize_action(rule)
        result[str(key)] = action
    return result


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _context_yolo_mode(context: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(context, dict):
        return False
    try:
        from domain.tool.schema_adapter import policy_from_context

        policy = policy_from_context(context)
    except Exception:
        policy = context.get("profile_policy") if isinstance(context.get("profile_policy"), dict) else {}
    return _truthy(policy.get("yolo_mode"))


def normalize_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = _deep_merge(_DEFAULT_POLICY, policy or {})
    raw["default_action"] = _normalize_action(raw.get("default_action"), _ACTION_ASK)
    raw["tools"] = _normalize_rule_map(raw.get("tools"))
    raw["tags"] = _normalize_rule_map(raw.get("tags"))
    raw["execution_types"] = _normalize_rule_map(raw.get("execution_types"))
    raw["mcp_servers"] = _normalize_rule_map(raw.get("mcp_servers"))
    raw["version"] = int(raw.get("version", 1) or 1)
    raw["updated_at"] = str(raw.get("updated_at", "") or "")
    return raw


class ToolPermissionPolicyStore:
    """Persist and evaluate a simple permission policy for tools."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else default_policy_path()

    def load(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return normalize_policy(_DEFAULT_POLICY)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return normalize_policy(_DEFAULT_POLICY)
        return normalize_policy(payload)

    def save(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_policy(policy)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return normalized

    def update(self, updates: Dict[str, Any], replace: bool = False) -> Dict[str, Any]:
        current = normalize_policy(updates) if replace else _deep_merge(self.load(), updates or {})
        return self.save(current)

    def evaluate(
        self,
        tool_name: str,
        tool_def: Optional[Dict[str, Any]] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        del arguments  # reserved for future policy predicates

        policy = self.load()
        tool = tool_def or {}
        execution = tool.get("execution", {}) if isinstance(tool, dict) else {}
        tags = tool.get("tags", []) if isinstance(tool, dict) else []
        tool_id = ""
        display_name = tool_name
        if isinstance(tool, dict):
            tool_id = str(tool.get("tool_id", "") or "")
            display_name = str(tool.get("name", "") or tool_name)

        matched_by = "default_action"
        matched_value = None
        action = policy["default_action"]

        candidates = [tool_name, tool_id, display_name]
        for candidate in candidates:
            if candidate and candidate in policy["tools"]:
                action = policy["tools"][candidate]
                matched_by = "tools"
                matched_value = candidate
                break

        if matched_by == "default_action":
            server_name = str(execution.get("server_name", "") or "")
            if server_name and server_name in policy["mcp_servers"]:
                action = policy["mcp_servers"][server_name]
                matched_by = "mcp_servers"
                matched_value = server_name

        if matched_by == "default_action":
            for tag in tags or []:
                if tag in policy["tags"]:
                    action = policy["tags"][tag]
                    matched_by = "tags"
                    matched_value = tag
                    break

        if matched_by == "default_action":
            execution_type = str(execution.get("type", "") or "")
            if execution_type and execution_type in policy["execution_types"]:
                action = policy["execution_types"][execution_type]
                matched_by = "execution_types"
                matched_value = execution_type

        if matched_by == "default_action" and isinstance(tool, dict) and is_safe_first_party_memo_tool(tool):
            action = _ACTION_ALLOW
            matched_by = "first_party_memo"
            matched_value = tool_id or display_name or tool_name

        allowed = action == _ACTION_ALLOW
        reason = ""
        if action == _ACTION_DENY:
            reason = "blocked_by_policy"
        elif action == _ACTION_ASK:
            reason = "approval_required"

        return {
            "tool_name": tool_name,
            "tool_id": tool_id or tool_name,
            "display_name": display_name,
            "action": action,
            "allowed": allowed,
            "requires_approval": action == _ACTION_ASK,
            "matched_by": matched_by,
            "matched_value": matched_value,
            "reason": reason,
            "policy": policy,
        }

    def decide(
        self,
        tool_name: str,
        tool_def: Optional[Dict[str, Any]] = None,
        arguments: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        decision = self.evaluate(tool_name=tool_name, tool_def=tool_def, arguments=arguments)
        if decision.get("action") == _ACTION_ASK and autonomous_tool_execution_allowed(tool_name, arguments, context):
            decision = copy.deepcopy(decision)
            decision["action"] = _ACTION_ALLOW
            decision["allowed"] = True
            decision["requires_approval"] = False
            decision["matched_by"] = "autonomous_profile"
            decision["matched_value"] = str((context or {}).get("profile_id") or "")
            decision["reason"] = "autonomous_profile"
            return decision
        if decision.get("action") == _ACTION_ASK and _context_yolo_mode(context):
            decision = copy.deepcopy(decision)
            decision["action"] = _ACTION_ALLOW
            decision["allowed"] = True
            decision["requires_approval"] = False
            decision["matched_by"] = "yolo_mode"
            decision["matched_value"] = "true"
            decision["reason"] = "yolo_mode"
        return decision

    def check(
        self,
        tool_name: str,
        tool_def: Optional[Dict[str, Any]] = None,
        arguments: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return bool(
            self.decide(
                tool_name=tool_name,
                tool_def=tool_def,
                arguments=arguments,
                context=context,
            ).get("allowed", False)
        )


_POLICY_STORE: Optional[ToolPermissionPolicyStore] = None


def get_tool_permission_policy_manager() -> ToolPermissionPolicyStore:
    global _POLICY_STORE
    if _POLICY_STORE is None:
        _POLICY_STORE = ToolPermissionPolicyStore()
    return _POLICY_STORE
